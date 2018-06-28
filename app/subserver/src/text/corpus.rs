use rayon::prelude::*;
use std::time::Duration;
use std::collections::{HashMap, HashSet};
use std::path::Path;
use std::fs;
use rayon;
use datatypes::{Document, Document_Word as Word, Document_PartOfSpeech as POS};
use protobuf::{Message, CodedInputStream};
use util::{CollectByKey, Merge, ParallelProgressIterator};
use text::index::Indexed;

impl Word {
    pub fn on_slice<'a: 'b, 'b>(&'a self, s: &'b str) -> &'b str {
        &s[(self.char_start as usize) .. (self.char_end as usize)]
    }
}

#[allow(dead_code)] // NOTE(wcrichto) 6-21-18: linter erroneously thinks text isn't used?
struct IndexedDocument<Index> {
    meta: Document,
    text: String,
    text_index: Index,
}

pub struct Corpus<Index> {
    docs: HashMap<String, IndexedDocument<Index>>
}

fn _duration_to_float(d: Duration) -> f64 {
    f64::from(d.as_secs() as u32) + f64::from(d.subsec_nanos()) / 1.0e-9
}

static SUB_CACHE_DIR: &'static str = "/app/data/subs";
static VALID_POS: &'static [POS] = {
    use self::POS::*;
    &[NN, NNS, NNP, NNPS, JJ, JJR, JJS, VB, VBD, VBG, VBN, VBP, VBZ, MD, FW, GW, SYM]
};

impl<Index: Indexed + Send> Corpus<Index> {
    pub fn new(paths: Vec<String>) -> Corpus<Index> {
        // For each subtitle file, load the corresponding flattened transcript and metadata
        let docs: HashMap<_, _> = paths.par_iter().progress_count(paths.len()).map(|path| {
            let item_name = path.split("/").last().unwrap().split(".").next().unwrap();
            let meta_path = format!("{}/meta/{}.bin", SUB_CACHE_DIR, item_name);
            let flat_path = format!("{}/flat/{}.txt", SUB_CACHE_DIR, item_name);

            // Ignore files that don't have metadata yet
            if !Path::new(&meta_path).exists() {
                return (path.clone(), None);
            }

            let doc: IndexedDocument<Index> = {
                // Decode metadata from protobuf
                let meta = {
                    let mut meta = Document::new();
                    // NB(wcrichto): reading it all at once and passing entire bytestring to decoder
                    // seems much faster than passing a file handle and letting decoder handle I/O.
                    // I think? Need to do more benchmarks to be sure. Perf seems kind of random
                    let mut s = fs::read(meta_path).expect("Meta file read failed");
                    let mut s = s.as_slice();
                    let mut bytes = CodedInputStream::new(&mut s);
                    meta.merge_from(&mut bytes).expect("Protobuf deserialize failed");
                    meta
                };

                // Load entire flat transcript as a string
                let text = fs::read_to_string(flat_path).expect("Text file read failed");

                IndexedDocument {
                    text: text.clone(),
                    // Dynamically construct search index over text
                    text_index: Index::new(text),
                    meta
                }
            };

            (path.clone(), Some(doc))
        }).filter(|(_, doc)| doc.is_some()).map(|(path, doc)| (path, doc.expect("Unreachable"))).collect();

        Corpus { docs }
    }

    fn find_with<T, F>(&self, s: String, f: F) -> HashMap<String, Vec<T>>
        where T: Send, F: (Fn(usize, &IndexedDocument<Index>) -> T) + Sync
    {
        self.docs.par_iter().map(|(path, doc)| {
            let mut pos = doc.text_index.positions_word(&s, &doc.meta);
            pos.sort();
            (path.clone(), pos.into_iter().map(|i| f(i, doc)).collect::<Vec<_>>())
        }).filter(|(_, v)| v.len() > 0).collect()
    }

    pub fn find<T: Into<String>>(&self, s: T) -> HashMap<String, Vec<(f64, f64)>> {
        let s: String = s.into();
        self.find_with(s, |i, doc| {
            let word = &doc.meta.words[i];
            (word.time_start as f64, word.time_end as f64)
        })
    }

    pub fn count<T: Into<String>>(&self, s: T) -> u64 {
        let s: String = s.into();
        self.find(s).into_iter().map(|(_, v)| v.len()).sum::<usize>() as u64
    }

    fn par_merge<T, F>(&self, v: &[T], f: &F) -> T
        where T: Sync + Send + Clone, F: Fn(T, T) -> T + Send + Sync
    {
        if v.len() > 1 {
            let (l, r) = v.split_at(v.len()/2);
            let (l, r) = rayon::join(
                || self.par_merge(l, f),
                || self.par_merge(r, f));
            f(l, r)
        } else {
            v[0].clone()
        }
    }

    fn _unique_words(&self) {
        let sets = self.docs.par_iter().progress_count(self.docs.len()).map(|(_, doc)| {
            doc.meta.words.iter()
                //.filter(|word| VALID_POS.contains(&word.pos))
                .map(|word| word.on_slice(&doc.text))
                .collect::<HashSet<_>>()
        }).collect::<Vec<_>>();

        let words = self.par_merge(&sets, &|a, b| &a | &b);
        println!("{}", words.len());
    }

    fn ngram_to_str(&self, ngram: &[Word]) -> String {
        ngram.iter().map(|w| w.lemma.as_str()).collect::<Vec<_>>().join(" ")
    }

    pub fn find_segments(&self, lexicon: Vec<String>) -> Vec<(String, (f32, f32), i32)> {
        let window_size = 500;
        let max_ngram = 3;
        let stride = 50;
        let target_bag = lexicon.iter().map(|s| s.as_str()).collect::<HashSet<_>>();
        let mut all_matches = self.docs.par_iter().progress_count(self.docs.len()).flat_map(|(path, doc)| {
            let matches = doc.meta.words
                .windows(window_size)
                .step_by(stride)
                .map(|window| {
                    let count = (1..=max_ngram).map(|n| {
                        window.windows(n).map(|ngram| {
                            if target_bag.contains::<str>(&self.ngram_to_str(ngram)) { 1 } else { 0 }
                        }).sum::<i32>()
                    }).sum::<i32>();
                    ((window.first().unwrap().time_start, window.last().unwrap().time_end), count)
                }).collect::<Vec<_>>();

            // TODO(wcrichto): condense overlapping segments

            matches.into_iter().map(|(i, n)| (path.clone(), i, n)).collect::<Vec<_>>()
        }).collect::<Vec<_>>();
        all_matches.sort_unstable_by(|(_, _, n1), (_, _, n2)| n2.cmp(n1));
        all_matches.truncate(100);
        all_matches
    }

    pub fn all_mutual_info(&self, s: impl Into<String>) -> Vec<(String, f64)> {
        let s: String = s.into();
        let max_ngram = 3;
        let span: i64 = 50;
        let ngram_fmap = |ngram: &[Word]| -> Option<String> {
            if ngram.iter().all(|w| VALID_POS.contains(&w.pos)) {
                Some(self.ngram_to_str(ngram))
            } else {
                None
            }
        };
        let (colo_counts, all_counts): (Vec<HashMap<_,_>>, Vec<HashMap<_,_>>) =
            self.docs.par_iter()
            .progress_count(self.docs.len())
            .map(|(_, doc)| {
                let words = &doc.meta.words;
                let word_indices = (1..=max_ngram)
                    .map(|n| {
                        words.windows(n)
                            .enumerate()
                            .filter_map(|(i, ngram)| ngram_fmap(ngram).map(|s| (s, i)))
                            .collect_by_key()
                    }).collect::<Vec<_>>();
                let word_indices = self.par_merge(
                    &word_indices,  &|mut a, b| { a.merge(b, |x, _y| x.clone()); a });

                let mut colo_count = HashMap::new();

                if let Some(idxs) = word_indices.get::<str>(&s) {
                    for idx in idxs.iter() {
                        let idx = *idx as i64;
                        let (start, end) = ((idx-span/2).max(0) as usize, ((idx+span/2) as usize).min(words.len()-1));
                        for n in 1..=max_ngram {
                            let ngrams = words.slice(start, end+1).windows(n).filter_map(ngram_fmap);
                            for s in ngrams {
                                let entry = colo_count.entry(s).or_insert(0);
                                *entry += 1;
                            }
                        }
                    }
                };
                (colo_count, word_indices.into_iter().map(|(k, v)| (k, v.len())).collect::<HashMap<_,_>>())
            })
            .collect::<Vec<_>>()
            .into_iter().unzip();
        let corpus: i64 =
            self.docs.par_iter().map(|(_, doc)| (doc.meta.words.len()) as i64).sum();

        let colo_total = self.par_merge(&colo_counts, &|mut a, b| { a.merge(b, |x, y| x + y); a});
        let all_total = self.par_merge(&all_counts, &|mut a, b| { a.merge(b, |x, y| x + y); a});

        let min_cooccur_threshold = 100;
        let min_occur_threshold = 1000;
        let mut counts = colo_total.keys().collect::<Vec<_>>().par_iter().filter_map(|k| {
            let ab = *colo_total.get::<str>(k).expect("ab") as f64;
            let a = *all_total.get::<str>(&s).expect("a") as f64;
            let b = *all_total.get::<str>(k).expect("b") as f64;
            let span = span as f64;
            let corpus = corpus as f64;
            let score = f64::log10(ab * corpus / (a * b * span)) / f64::log10(2.0);

            if ab as i64 > min_cooccur_threshold &&
                b as i64 > min_occur_threshold {
                Some((k.to_string(), score))
            } else {
                None
            }
        }).collect::<Vec<_>>();

        counts.sort_unstable_by(|(_, a), (_, b)| b.partial_cmp(a).unwrap());
        counts.truncate(1000);
        counts
    }
}
