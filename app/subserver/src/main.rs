#![feature(proc_macro, specialization, plugin)]
#![plugin(rocket_codegen)]

extern crate serde;
#[macro_use] extern crate serde_derive;
#[macro_use] extern crate lazy_static;
extern crate glob;
extern crate rayon;
extern crate srtparse;
extern crate suffix;
extern crate indicatif;
extern crate rocket;
extern crate rocket_contrib;

use std::time::Instant;
use glob::glob;
use rayon::prelude::*;
use std::time::Duration;
use suffix::SuffixTable;
use std::collections::{HashMap, BTreeMap};
use indicatif::ProgressBar;
use rocket_contrib::Json;
use rocket::config::{Config, Environment};
use std::sync::Mutex;

struct Document {
    text_index: SuffixTable<'static, 'static>,
    time_index: BTreeMap<u32, (f64, f64)>
}

struct Corpus {
    docs: HashMap<String, Document>
}

fn duration_to_float(d: Duration) -> f64 {
    f64::from(d.as_secs() as u32) + f64::from(d.subsec_nanos()) / 1.0e-9
}

impl Corpus {
    pub fn new(paths: Vec<String>) -> Corpus {
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
                    let text_index = SuffixTable::new(text);

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
            let mut pos = Vec::new();
            pos.extend_from_slice(doc.text_index.positions(&s));
            pos.sort();
            (path.clone(), pos.into_iter().map(|i| {
                let (_, val) = doc.time_index.range(..(i+1)).next_back().expect("Missing time key");
                val.clone()
            }).collect::<Vec<_>>())
        }).filter(|(_, v)| v.len() > 0).collect()
    }
}

lazy_static! {
    static ref CORPUS: Corpus  = {
        let paths: Vec<_> = glob("/app/subs/*").expect("Glob failed")
            .filter_map(|s| match s {
                Ok(p) => {
                    Some(p.to_str().expect("Path -> str failed").to_string())
                }
                Err(_) => None })
            .collect();
        Corpus::new(paths)
    };
}

struct BlockTimer {
    name: String,
    start: Instant
}

impl BlockTimer {
    pub fn new<T: Into<String> + Clone>(name: T) -> BlockTimer {
        println!("Starting: {}", name.clone().into());
        BlockTimer {
            name: name.into(),
            start: Instant::now()
        }
    }
}

impl Drop for BlockTimer {
    fn drop(&mut self) {
        println!("Finished: {} in {}s", self.name, self.start.elapsed().as_secs());
    }
}

#[derive(Serialize, Deserialize)]
struct FindInput {
    phrase: String
}

#[post("/find", format="application/json", data="<input>")]
fn find(input: Json<FindInput>) -> Json<HashMap<String, Vec<(f64, f64)>>> {
    Json(CORPUS.find(input.phrase.clone()))
}

fn main() {
    let config = Config::build(Environment::Development)
        .port(8111)
        .unwrap();
    rocket::custom(config, true).mount("/", routes![find]).launch();
}
