use rayon::prelude::*;
use std::time::Duration;
use suffix::SuffixTable;
use std::collections::{HashMap, BTreeMap};
use indicatif::ProgressBar;
use std::sync::Mutex;
use srtparse;

pub trait Indexed: Send {
    fn new(s: String) -> Self;
    fn positions(&self, query: &str) -> Vec<u32>;
}

impl Indexed for SuffixTable<'static, 'static> {
    fn new(s: String) -> Self {
        SuffixTable::new(s)
    }

    fn positions(&self, query: &str) -> Vec<u32> {
        let mut v = Vec::new();
        v.extend_from_slice(self.positions(query));
        v
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
}

struct Document<TextIndex> {
    text_index: TextIndex,
    time_index: BTreeMap<u32, (f64, f64)>
}

pub struct Corpus<TextIndex> {
    docs: HashMap<String, Document<TextIndex>>
}

fn duration_to_float(d: Duration) -> f64 {
    f64::from(d.as_secs() as u32) + f64::from(d.subsec_nanos()) / 1.0e-9
}

impl<TextIndex: Indexed> Corpus<TextIndex> {
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
                    let text_index = TextIndex::new(text);

                    Some(Document {text_index, time_index})
                },
                Err(_) => None
            };
            pb.lock().unwrap().inc(1);
            (path.clone(), doc)
        }).filter(|(_, doc)| doc.is_some()).map(|(path, doc)| (path, doc.expect("Unreachable"))).collect();
        Corpus { docs }
    }

    pub fn find<T: Into<String>>(&self, s: T) -> HashMap<String, Vec<(f64, f64)>> {
        let s: String = s.into();
        self.docs.iter().map(|(path, doc)| {
            let mut pos = doc.text_index.positions(&s);
            pos.sort();
            (path.clone(), pos.into_iter().map(|i| {
                let (_, val) = doc.time_index.range(..(i+1)).next_back().expect("Missing time key");
                val.clone()
            }).collect::<Vec<_>>())
        }).filter(|(_, v)| v.len() > 0).collect()
    }
}
