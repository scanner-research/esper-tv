use rayon::prelude::*;
use std::time::Duration;
use std::collections::{HashSet, HashMap};
use std::collections::hash_map::Entry;
use std::path::Path;
use std::fs;
use rayon;
use datatypes::{
    Document, Document_Word as Word, Document_PartOfSpeech as POS,
    DocsVectors, DocsVectors_DocVectors as DocVectors, DocsVectors_DocVectors_Vector as SegVector};
use protobuf::{Message, CodedInputStream, CodedOutputStream, RepeatedField};
use util::{CollectByKey, Merge, ProgressIterator, ParallelProgressIterator};
use text::index::Indexed;
use byteorder::{LittleEndian, WriteBytesExt};
use std::io::Write;

// use std::collections::HashMap;
// pub type Map<K, V> = HashMap<K, V>;

use fnv::FnvHashMap;
pub type Map<K, V> = FnvHashMap<K, V>;

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

#[derive(Copy, Clone)]
pub struct Interval {
    time_start: f64,
    time_end: f64,
}

pub struct Corpus<Index> {
    docs: Map<String, IndexedDocument<Index>>
}

fn _duration_to_float(d: Duration) -> f64 {
    f64::from(d.as_secs() as u32) + f64::from(d.subsec_nanos()) / 1.0e-9
}

static SUB_CACHE_DIR: &'static str = "/app/data/subs";
static VALID_POS: &'static [POS] = {
    use self::POS::*;
    //&[NN, NNS, NNP, NNPS, JJ, JJR, JJS, VB, VBD, VBG, VBN, VBP, VBZ, MD, FW, GW, SYM]
    &[NN, NNS, NNP, NNPS]
};

impl<Index: Indexed + Send> Corpus<Index> {
    pub fn new(paths: Vec<String>) -> Corpus<Index> {
        // For each subtitle file, load the corresponding flattened transcript and
        // let path_iter = paths.par_iter();
        let path_iter = paths.par_iter().take(10000);
        let docs: Map<_, _> = path_iter.progress_count(paths.len()).map(|path| {
            let item_name = path.split("/").last().unwrap().split(".").next().unwrap().to_string();
            let meta_path = format!("{}/meta/{}.bin", SUB_CACHE_DIR, item_name);
            let flat_path = format!("{}/flat/{}.txt", SUB_CACHE_DIR, item_name);

            // Ignore files that don't have metadata yet
            if !Path::new(&meta_path).exists() {
                return (item_name.clone(), None);
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

            (item_name.clone(), Some(doc))
        }).filter(|(_, doc)| doc.is_some()).map(|(path, doc)| (path, doc.expect("Unreachable"))).collect();

        Corpus { docs }
    }

    pub fn videos(&self) -> Vec<String> {
        let mut v: Vec<_> = self.docs.keys().cloned().collect();
        v.sort();
        v
    }

    pub fn doc_len(&self) -> HashMap<String, usize> {
        self.docs.iter().map(|(key, doc)| (key.clone(), doc.meta.words.len())).collect()
    }

    fn find_with<T, F>(&self, s: String, f: F) -> Map<String, Vec<T>>
        where T: Send, F: (Fn(usize, &IndexedDocument<Index>) -> T) + Sync
    {
        self.docs.par_iter().map(|(path, doc)| {
            let mut pos = doc.text_index.positions_word(&s, &doc.meta);
            pos.sort();
            (path.clone(), pos.into_iter().map(|i| f(i, doc)).collect::<Vec<_>>())
        }).filter(|(_, v)| v.len() > 0).collect()
    }

    pub fn find<T: Into<String>>(&self, s: T) -> Map<String, Vec<(f64, f64)>> {
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

    pub fn word_counts(&self) -> HashMap<String, usize> {
        let counts: Vec<HashMap<String, usize>> = self.docs.par_iter().progress_count(self.docs.len()).map(|(_, doc)| {
            doc.meta.words.iter()
                .filter(|word| VALID_POS.contains(&word.pos))
                .map(|word| word.lemma.as_str())
                .fold(HashMap::new(), |mut map, w| {
                    *map.entry(w.to_string()).or_insert(0) += 1;
                    map
                })
        }).collect();

        self.par_merge(&counts, &|a, b| {
            let mut a = a.clone();
            for (k, v) in b {
                *a.entry(k).or_insert(0) += v;
            }
            a
        })
    }

    fn ngram_to_str(&self, ngram: &[Word]) -> String {
        ngram.iter().map(|w| w.lemma.as_str()).collect::<Vec<_>>().join(" ")
    }

    pub fn get_doc(&self, doc: String) -> Vec<String> {
        self.docs[&doc].meta.words.iter().map(|word| word.lemma.as_str().to_string()).collect::<Vec<String>>()
    }

    pub fn compute_vectors(&self, vocabulary: Vec<String>, window_size: usize, stride: usize, docs: Vec<String>) {
        let mut f = fs::File::create(format!("/app/data/segvectors.bin")).unwrap();
        for doc_name in docs.iter().progress_count(docs.len()) {
            let doc = &self.docs[doc_name];
            let vec = doc.meta.words
                .windows(window_size).step_by(stride)
                .flat_map(|window| {
                    let max_ngram = 3;
                    let mut map = HashMap::new();
                    let word_iter = (1..=max_ngram)
                        .flat_map(|n| {
                            window.windows(n).map(|ngram| self.ngram_to_str(ngram))
                                .collect::<Vec<_>>()
                        });
                    for word in word_iter {
                        *map.entry(word).or_insert(0) += 1;
                    }

                    vocabulary.iter().map(|w| {
                        map.get(w).map(|n| *n).unwrap_or(0)
                    }).collect::<Vec<_>>()
                })
                .collect::<Vec<_>>();

            f.write_all(&vec).unwrap();
        }
    }

    pub fn find_segments(&self, lexicon: Vec<(String, f64)>, stride: usize, window_size: usize, min_score_threshold: f64,
                         merge_overlaps: bool, doc_set: HashSet<String>
    ) -> Vec<(String, (f32, f32), usize, f64, Map<String, usize>)>
    {
        let max_ngram = 3;
        let target_scores = lexicon.iter().map(|(s, score)| (s.as_str(), score)).collect::<Map<_, _>>();

        #[derive(Clone)]
        struct Segment {
            time_start: f32,
            time_end: f32,
            word_start: usize,
            count: f64,
            words: Map<String, usize>
        }

        // For each document:
        let mut all_matches = self.docs.par_iter().filter(
            |(path, _)| if doc_set.is_empty() { true } else { doc_set.contains(*path) }
        ).progress_count(
            self.docs.len()
        ).flat_map(|(path, doc)| {
            // For each segment window, convolve with lexicon to produce segment score
            let matches = doc.meta.words
                .windows(window_size)
                .enumerate()
                .step_by(stride)
                .map(|(idx, window)| {
                    let (words, counts): (Vec<_>, Vec<_>) = (1..=max_ngram).flat_map(|n| {
                        window.windows(n).map(|ngram| {
                            let ngram_str = self.ngram_to_str(ngram);
                            match target_scores.get::<str>(&ngram_str) {
                                Some(n) => (Some(ngram_str), **n),
                                None => (None, 0.0)
                            }
                        }).collect::<Vec<_>>()
                    }).unzip();

                    let mut word_count = Map::default();
                    for word in words {
                        if let Some(s) = word {
                            *word_count.entry(s).or_insert(0) += 1
                        }
                    }

                    Segment {
                        time_start: window.first().unwrap().time_start,
                        time_end: window.last().unwrap().time_end,
                        word_start: idx,
                        count: counts.into_iter().sum::<f64>(),
                        words: word_count
                    }
                }).collect::<Vec<_>>();

            // Filter segments less than an small absolute threshold
            let mut matches = matches.into_iter().filter(|seg| seg.count > min_score_threshold).collect::<Vec<_>>();

            // Merge overlapping segments
            if matches.len() == 0 {
                vec![]
            } else {
                let collapse_segs = |segs: &Vec<Segment>| -> Segment {
                    let mut words: Map<String, usize> = Map::default();

                    // TODO: do this in a more reasonable way. This takes the max.
                    for seg in segs {
                        for (key, val) in &seg.words {
                            match words.entry(key.to_string()) {
                                Entry::Occupied(o) => {
                                    if *o.get() < *val {
                                        *o.into_mut() = *val;
                                    };
                                },
                                Entry::Vacant(v) => {
                                    v.insert(*val);
                                }
                            };
                        }
                    }

                    Segment {
                        time_start: segs.first().unwrap().time_start,
                        time_end: segs.last().unwrap().time_end,
                        word_start: segs.first().unwrap().word_start,
                        count: segs.iter().map(|seg| seg.count).sum::<f64>() / (segs.len() as f64),
                        words: words
                    }
                };

                let reduced_segs = if merge_overlaps {
                    let first = matches.remove(0);
                    let (mut reduced_segs, last) = matches.into_iter().fold(
                        (vec![], vec![first]), |(mut acc, mut last_segs), cur_seg| {
                            let overlaps = {
                                let last_seg = last_segs.last().unwrap();
                                last_seg.time_end >= cur_seg.time_start &&
                                    last_seg.time_start <= cur_seg.time_end
                            };

                            if overlaps {
                                last_segs.push(cur_seg);
                                (acc, last_segs)
                            } else {
                                acc.push(collapse_segs(&last_segs));
                                (acc, vec![cur_seg])
                            }
                        });
                    reduced_segs.push(collapse_segs(&last));
                    reduced_segs
                } else {
                    matches
                };

                reduced_segs.into_iter().map(|seg| (path.clone(), (seg.time_start, seg.time_end), seg.word_start, seg.count, seg.words))
                    .collect::<Vec<_>>()
            }

        }).collect::<Vec<_>>();

        // Return top k segments
        all_matches.sort_unstable_by(|(_, _, _, n1, _), (_, _, _, n2, _)| n2.partial_cmp(n1).unwrap());
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

        // Compute colocation and total counts for all words in corpus
        let (colo_counts, all_counts): (Vec<Map<_,_>>, Vec<Map<_,_>>) =
            self.docs.par_iter()
            .progress_count(self.docs.len())
            .map(|(_, doc)| {
                let words = &doc.meta.words;
                let word_indices_nested = (1..=max_ngram)
                    .map(|n| {
                        words.windows(n)
                            .enumerate()
                            .filter_map(|(i, ngram)| ngram_fmap(ngram).map(|s| (s, i)))
                            .collect_by_key()
                    }).collect::<Vec<_>>();

                // word_indices maps {string => list of indices where the string occurs in doc}
                let word_indices = self.par_merge(
                    &word_indices_nested,  &|mut a, b| { a.merge(b, |x, _y| x.clone()); a });

                let mut colo_count = Map::default();

                if let Some(idxs) = word_indices.get::<str>(&s) {
                    // for each occurrence of the target word, increment the colocation count of
                    // every n-gram in a window around the target
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
                (colo_count, word_indices.into_iter().map(|(k, v)| (k, v.len())).collect::<Map<_,_>>())
            })
            .collect::<Vec<_>>()
            .into_iter().unzip();

        let corpus_size: i64 =
            self.docs.par_iter().map(|(_, doc)| (doc.meta.words.len()) as i64).sum();

        // colo_total is {string => co-occurrence of string with target}
        // all_total is {string => total occurrence of string in corpus}
        let colo_total = self.par_merge(&colo_counts, &|mut a, b| { a.merge(b, |x, y| x + y); a});
        let all_total = self.par_merge(&all_counts, &|mut a, b| { a.merge(b, |x, y| x + y); a});

        let min_cooccur_threshold = 100;
        let min_occur_threshold = 1000;

        let mut counts = colo_total.keys().collect::<Vec<_>>().par_iter().filter_map(|k| {
            let ab = *colo_total.get::<str>(k).expect("ab") as f64;
            let a = *all_total.get::<str>(&s).expect("a") as f64;
            let b = *all_total.get::<str>(k).expect("b") as f64;
            let span = span as f64;
            let corpus_size = corpus_size as f64;

            // Mutual information formula from:
            // http://journals.plos.org/plosone/article?id=10.1371/journal.pone.0062343
            let score = f64::log10(ab * corpus_size / (a * b * span)) / f64::log10(2.0);

            if ab as i64 > min_cooccur_threshold &&
                b as i64 > min_occur_threshold {
                Some((k.to_string(), score))
            } else {
                None
            }
        }).collect::<Vec<_>>();

        let min_score_threshold = 3.0;
        counts.sort_unstable_by(|(_, a), (_, b)| b.partial_cmp(a).unwrap());
        counts.into_iter().filter(|(_, score)| *score > min_score_threshold).collect::<Vec<_>>()
    }

    pub fn lowercase_segments(&self) -> Vec<(String, f64, f64)> {
        self.docs.par_iter().filter_map(|(path, doc)| {
            let chars : Vec<char> = doc.text.chars().collect();

            let mut segments = doc.meta.words.par_iter().filter_map(|w| {
                for i in w.char_start..w.char_end {
                    if chars[i as usize].is_lowercase() {
                        return Some(Interval {
                            time_start : w.time_start as f64,
                            time_end : w.time_end as f64 })
                    }
                }
                None
            }).collect::<Vec<Interval>>();

            segments.sort_by(|interval1, interval2|
                             interval1.time_start.partial_cmp(
                                &interval2.time_start).unwrap());

            let mut smashed_vector : Vec<(String, f64, f64)> = Vec::new();
            if segments.len() > 0 {
                let mut first = segments[0];
                for segment in segments {
                    if segment.time_start >= first.time_start
                        && segment.time_start <= first.time_end {
                        // segment overlaps with first
                        if segment.time_end > first.time_end {
                            // need to push the upper bound
                            first.time_end = segment.time_end
                        }
                    } else {
                        // segment does not overlap with first
                        smashed_vector.push((path.clone(), first.time_start,
                                             first.time_end));
                        first = segment;
                    }
                }
                smashed_vector.push((path.clone(), first.time_start,
                    first.time_end));
            }

            if smashed_vector.len() > 0 {
                Some(smashed_vector)
            } else {
                None
            }
        })
        .progress_count(self.docs.len())
        .flatten()
        .collect()
    }
}
