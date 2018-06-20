use rayon::prelude::*;
use std::time::Duration;
use suffix::SuffixTable;
use std::collections::{HashMap, BTreeSet, HashSet};
use std::sync::{Mutex};
use srtparse;
use std::cell::RefCell;
use std::path::Path;
use std::fs;
use std::panic;
use progress::{ParallelProgressIterator, ProgressIterator};
use rayon;
use std::hash::Hash;
use datatypes::{Document, Document_Word as Word, Document_PartOfSpeech as POS};
use protobuf::{Message, CodedInputStream};
use std::fs::File;

trait CollectByKey {
    type Key: Eq + Hash;
    type Value;
    fn collect_by_key(self) -> HashMap<Self::Key, Vec<Self::Value>>;
}

impl<Key, Value, T> CollectByKey for T where Key: Eq + Hash, T: Iterator<Item=(Key, Value)> {
    type Key = Key;
    type Value = Value;

    fn collect_by_key(self) -> HashMap<Self::Key, Vec<Self::Value>> {
        let mut map = HashMap::new();
        for (k, v) in self {
            let mut list = map.entry(k).or_insert_with(|| vec![]);
            list.push(v);
        }

        map
    }
}

trait WordIndex {
    fn on_slice<'a: 'b, 'b>(&'a self, s: &'b str) -> &'b str;
}

impl WordIndex for Word {
    fn on_slice<'a: 'b, 'b>(&'a self, s: &'b str) -> &'b str {
        &s[(self.char_start as usize) .. (self.char_end as usize)]
    }
}

trait Merge {
    type Key;
    type Value;

    fn merge<F>(&mut self, other: HashMap<Self::Key, Self::Value>, f: F)
        where F: Fn(&Self::Value, &Self::Value) -> Self::Value;
}

impl<Key, Value> Merge for HashMap<Key, Value> where Key: Hash + Eq {
    type Key = Key;
    type Value = Value;

    fn merge<F>(&mut self, other: HashMap<Self::Key, Self::Value>, f: F)
        where F: Fn(&Self::Value, &Self::Value) -> Self::Value
    {
        for (k, v) in other {
            if self.contains_key(&k) {
                let merged = f(self.get(&k).unwrap(), &v);
                self.insert(k, merged);
            } else {
                self.insert(k, v);
            }
        }
    }
}

struct IndexedDocument<Index> {
    meta: Document,
    text: String,
    text_index: Index,
}

pub struct Corpus<Index> {
    docs: HashMap<String, IndexedDocument<Index>>
}

pub trait Indexed: Send + Sync {
    fn new(s: String) -> Self;

    fn positions_char(&self, query: &str) -> Vec<usize>;

    fn positions_word(&self, query: &str, meta: &Document) -> Vec<usize> {
        let pos = self.positions_char(query);

        let word_index =
            meta.words.iter().enumerate().map(|(i, w)| (w.char_start as usize, i)).collect::<HashMap<_,_>>();

        pos.into_iter().filter_map(|i| word_index.get(&i)).cloned().collect::<Vec<_>>()
    }
}


pub struct IndexedTable {
    table: SuffixTable<'static, 'static>
}

impl Indexed for IndexedTable {
    fn new(s: String) -> Self {
        IndexedTable {
            table: SuffixTable::new(s)
        }
    }

    fn positions_char(&self, query: &str) -> Vec<usize> {
        let mut v = Vec::new();
        v.extend_from_slice(&self.table.positions(query).into_iter().map(|i| *i as usize).collect::<Vec<_>>());
        v
    }
}


pub struct WordSearch {
    text: String
}

impl Indexed for WordSearch {
    fn new(s: String) -> Self { WordSearch { text: s } }

    fn positions_char(&self, query: &str) -> Vec<usize> {
        panic!()
    }

    fn positions_word(&self, query: &str, meta: &Document) -> Vec<usize> {
        let parts = query.split(" ").collect::<Vec<_>>();
        meta.words.windows(parts.len()).enumerate().filter(|(_, window)| {
            parts.iter().zip(window.iter()).all(|(i, j)| i == &j.on_slice(&self.text))
        }).map(|(i, _)| i).collect::<Vec<_>>()
    }
}

fn duration_to_float(d: Duration) -> f64 {
    f64::from(d.as_secs() as u32) + f64::from(d.subsec_nanos()) / 1.0e-9
}

static SUB_CACHE_DIR: &'static str = "/app/data/subs";
static VALID_POS: &'static [POS] = {
    use self::POS::*;
    &[NN, NNS, NNP, NNPS, JJ, JJR, JJS, VB, VBD, VBG, VBN, VBP, VBZ, MD, FW, GW, SYM]
};

impl<Index: Indexed + Send> Corpus<Index> {
    pub fn new(paths: Vec<String>) -> Corpus<Index> {
        let docs: HashMap<_, _> = paths.par_iter().progress_count(paths.len()).map(|path| {
            let item_name = path.split("/").last().unwrap().split(".").next().unwrap();
            let meta_path = format!("{}/meta/{}.bin", SUB_CACHE_DIR, item_name);
            let flat_path = format!("{}/flat/{}.txt", SUB_CACHE_DIR, item_name);

            if !Path::new(&meta_path).exists() {
                return (path.clone(), None);
            }

            let doc: IndexedDocument<Index> = {
                let meta = {
                    let mut meta = Document::new();
                    // NB(wcrichto): reading it all at once and passing entire bytestring to decoder
                    // seems much faster than passing a file handle and letting decoder handle I/O.
                    let mut s = fs::read(meta_path).expect("Meta file read failed");
                    let mut s = s.as_slice();
                    let mut bytes = CodedInputStream::new(&mut s);
                    meta.merge_from(&mut bytes).expect("Protobuf deserialize failed");
                    meta
                };

                let text = fs::read_to_string(flat_path).expect("Text file read failed");

                IndexedDocument {
                    text: text.clone(),
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

    fn unique_words(&self) {
        let sets = self.docs.par_iter().progress_count(self.docs.len()).map(|(_, doc)| {
            doc.meta.words.iter()
                .filter(|word| VALID_POS.contains(&word.pos))
                .map(|word| word.on_slice(&doc.text))
                .collect::<HashSet<_>>()
        }).collect::<Vec<_>>();

        let words = self.par_merge(&sets, &|a, b| &a | &b);
        println!("{}", words.len());
    }

    pub fn all_mutual_info(&self, s: impl Into<String>) -> HashMap<String, f64> {
        let s: String = s.into();
        let span = 50;
        let (colo_counts, all_counts): (Vec<HashMap<_,_>>, Vec<HashMap<_,_>>) =
            self.docs.par_iter()
            .progress_count(self.docs.len())
            .map(|(_, doc)| {
                let words = &doc.meta.words;
                let word_indices = words.iter()
                    .enumerate()
                    .filter(|(_, word)| VALID_POS.contains(&word.pos))
                    .map(|(i, word)| (word.lemma.as_str(), i))
                    .collect_by_key();

                let mut colo_count = HashMap::new();

                if let Some(idxs) = word_indices.get::<str>(&s) {
                    for idx in idxs.iter() {
                        let span = span as i64;
                        let idx = *idx as i64;
                        let (start, end) = ((idx-span/2).max(0) as usize, ((idx+span/2) as usize).min(words.len()-1));
                        for word in (words.slice(start, end+1)).iter().filter(|word| VALID_POS.contains(&word.pos)) {
                            let entry = colo_count.entry(word.lemma.as_str()).or_insert(0);
                            *entry += 1;
                        }
                    }
                };
                (colo_count, word_indices.into_iter().map(|(k, v)| (k, v.len())).collect::<HashMap<_,_>>())
            })
            .collect::<Vec<_>>()
            .into_iter().unzip();
        let corpus: i64 = self.docs.par_iter().map(|(_, doc)| doc.meta.words.len() as i64).sum();

        let colo_total = self.par_merge(&colo_counts, &|mut a, b| { a.merge(b, |x, y| x + y); a});
        let all_total = self.par_merge(&all_counts, &|mut a, b| { a.merge(b, |x, y| x + y); a});

        let min_cooccur_threshold = 100;
        let min_occur_threshold = 1000;
        colo_total.keys().filter_map(|k| {
            let ab = *colo_total.get(k).expect("ab") as f64;
            let a = *all_total.get::<str>(&s).expect("a") as f64;
            let b = *all_total.get(k).expect("b") as f64;
            let span = span as f64;
            let corpus = corpus as f64;
            let score = f64::log10(ab * corpus / (a * b * span)) / f64::log10(2.0);

            if ab as i64 > min_cooccur_threshold && b as i64 > min_occur_threshold {
                Some((k.to_string(), score))
            } else {
                None
            }
        }).collect::<HashMap<_,_>>()
    }
}
