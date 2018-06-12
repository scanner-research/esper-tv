use rayon::prelude::*;
use std::time::Duration;
use suffix::SuffixTable;
use std::collections::{HashMap, BTreeMap, BTreeSet, HashSet};
use indicatif::ProgressBar;
use std::sync::Mutex;
use srtparse;

pub trait Indexed: Send + Sync {
    fn new(s: String) -> Self;
    fn positions(&self, query: &str) -> Vec<u32>;
    fn len(&self) -> usize;
}

fn tokenize(s: &str) -> BTreeMap<usize, usize> {
    let mut words = BTreeMap::new();
    let mut start = 0;
    for (i, c) in s.char_indices() {
        if c == ' ' {
            words.insert(start as usize, (i-1) as usize);
            start = i+1;
        }
    }
    words
}

pub type IndexedTable = SuffixTable<'static, 'static>;

impl Indexed for IndexedTable {
    fn new(s: String) -> Self {
        SuffixTable::new(s)
    }

    fn positions(&self, query: &str) -> Vec<u32> {
        let mut v = Vec::new();
        v.extend_from_slice(self.positions(query));
        v
    }

    fn len(&self) -> usize {
        self.len()
    }
}


pub struct LinearSearch {
    text: String
}

impl Indexed for LinearSearch {
    fn new(s: String) -> Self {
        LinearSearch {
            text: s
        }
    }

    fn positions(&self, query: &str) -> Vec<u32> {
        self.text.match_indices(query).map(|(i, _)| i as u32).collect::<Vec<_>>()
    }

    fn len(&self) -> usize {
        self.text.len()
    }
}


// pub struct Tokenized {
//     tokens: Vec<String>
// }

// impl Indexed for Tokenized {
//     fn new(s: String) -> Self {
//         Tokenized {
//             tokens: tokenize(&s)
//         }
//     }

//     fn positions(&self, query: &str) -> Vec<u32> {
//         let querytok = tokenize(query);
//         let n = querytok.len();
//         let mut matches = Vec::new();
//         for i in 0..(self.tokens.len() - n) {
//             let mut does_match = true;
//             for j in 0..n {
//                 if self.tokens[i] != querytok[j] {
//                     does_match = false;
//                     break;
//                 }
//             }

//             if does_match {
//                 matches.push(i as u32);
//             }
//         }

//         matches
//     }

//     fn len(&self) -> usize {
//         self.tokens.len()
//     }
// }


struct Document<TextIndex> {
    text_index: TextIndex,
    word_set: BTreeMap<usize, usize>,
    time_index: BTreeMap<u32, (f64, f64)>,
    text: String
}

pub struct Corpus<TextIndex> {
    docs: HashMap<String, Document<TextIndex>>
}

fn duration_to_float(d: Duration) -> f64 {
    f64::from(d.as_secs() as u32) + f64::from(d.subsec_nanos()) / 1.0e-9
}

impl<TextIndex: Indexed+Send> Corpus<TextIndex> {
    pub fn new(paths: Vec<String>) -> Corpus<TextIndex> {
        let pb = Mutex::new(ProgressBar::new(paths.len() as u64));
        let docs: HashMap<_, _> = paths.par_iter().map(|path| {
            let doc = match srtparse::read_from_file(&path) {
                Ok(captions) => {
                    let mut text = String::new();
                    let mut time_index = BTreeMap::new();
                    let mut cursor = 0;
                    for caption in captions {
                        text += &caption.text;
                        time_index.insert(
                            cursor as u32,
                            (duration_to_float(caption.start_time), duration_to_float(caption.end_time)));
                        cursor += caption.text.len();
                    }
                    let word_set = tokenize(&text);
                    let text_index = TextIndex::new(text.clone());

                    Some(Document {text_index, word_set, time_index, text})
                },
                Err(_) => None
            };
            pb.lock().unwrap().inc(1);
            (path.clone(), doc)
        }).filter(|(_, doc)| doc.is_some()).map(|(path, doc)| (path, doc.expect("Unreachable"))).collect();
        Corpus { docs }
    }

    fn find_with<T, F>(&self, s: String, f: F) -> HashMap<String, Vec<T>>
        where T: Send, F: (Fn(u32, &Document<TextIndex>) -> T) + Sync
    {
        self.docs.par_iter().map(|(path, doc)| {
            let mut pos = doc.text_index.positions(&s);
            pos.sort();
            (path.clone(), pos.into_iter().map(|i| f(i, doc)).collect::<Vec<_>>())
        }).filter(|(_, v)| v.len() > 0).collect()
    }

    pub fn find<T: Into<String>>(&self, s: T) -> HashMap<String, Vec<(f64, f64)>> {
        let s: String = s.into();
        self.find_with(s, |i, doc| {
            let (_, val) = doc.time_index.range(..(i+1)).next_back().expect("Missing time key");
            val.clone()
        })
    }

    pub fn count<T: Into<String>>(&self, s: T) -> u64 {
        let s: String = s.into();
        let n: usize = self.docs.par_iter().map(|(_, doc)| {
            doc.text_index.positions(&s).len()
        }).sum();
        n as u64
    }

    fn unique_words(&self) {
        let sets = self.docs.par_iter().map(|(_, doc)| {
            let mut all_words = HashSet::new();
            for (i, j) in doc.word_set.iter() {
                all_words.insert(&doc.text[*i..*j]);
            }
            all_words
        }).collect::<Vec<_>>();
        let words = sets.into_iter().fold(HashSet::new(), |acc, set| &acc | &set);
        println!("{}", words.len());
    }

    pub fn mutual_information<T1: Into<String>, T2: Into<String>>(&self, s1: T1, s2: T2, span: i64) -> f64 {
        let s1: String = s1.into();
        let s2: String = s2.into();
        let pos1 = self.find_with(s1, |i, doc| i);
        let pos2 = self.find_with(s2, |i, doc| i);

        self.unique_words();

        #[derive(Clone, Copy, Debug)]
        struct MutualInfo {
            a: i64,
            b: i64,
            ab: i64,
            corpus: i64
        }

        let default_info = MutualInfo { a: 0, b: 0, ab: 0, corpus: 0 };

        let info = self.docs.keys().collect::<Vec<_>>().into_par_iter().map(|path| {
            if !pos1.contains_key(path) || !pos2.contains_key(path) {
                return default_info;
            }

            let pos1_doc = &pos1[path];
            let pos2_doc = &pos2[path];

            let ab = pos1_doc.iter().map(|i| {
                let mindist = pos2_doc.iter().map(|j| ((*i as i64) - (*j as i64)).abs()).min().unwrap_or(100000);
                if mindist <= (span*6)/2 { 1 } else { 0 }
            }).sum();

            MutualInfo {
                a: pos1_doc.len() as i64,
                b: pos2_doc.len() as i64,
                corpus: self.docs[path].text_index.len() as i64,
                ab
            }
        }).collect::<Vec<_>>();

        let total_info = info.into_iter().fold(default_info, |acc, info| {
            MutualInfo {
                a: acc.a + info.a,
                b: acc.b + info.b,
                ab: acc.ab + info.ab,
                corpus: acc.corpus + info.corpus
            }
        });

        println!("{:?}", total_info);
        f64::log10(
            ((total_info.ab as f64) * (total_info.corpus as f64))
                / ((total_info.a as f64) * (total_info.b as f64) * (span as f64)))
            / f64::log10(2.0)
    }
}
