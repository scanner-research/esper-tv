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
extern crate ndarray;
extern crate byteorder;

use rocket_contrib::Json;
use rocket::config::{Config, Environment};
use glob::glob;
use std::collections::HashMap;
use ndarray::Array;

use block_timer::BlockTimer;
use corpus::Corpus;
use knn::{Features, Target};

mod knn;
mod corpus;
mod block_timer;

lazy_static! {
    static ref CORPUS: Corpus<corpus::LinearSearch>  = {
        let paths: Vec<_> = glob("/app/subs/*").expect("Glob failed")
            .filter_map(|s| match s {
                Ok(p) => {
                    Some(p.to_str().expect("Path -> str failed").to_string())
                }
                Err(_) => None })
            .collect();
        Corpus::new(paths)
    };

    static ref FEATURES: Features = {
        Features::new()
    };
}

#[derive(Serialize, Deserialize)]
struct SubSearchInput {
    phrase: String
}

#[post("/subsearch", format="application/json", data="<input>")]
fn sub_search(input: Json<SubSearchInput>) -> Json<HashMap<String, Vec<(f64, f64)>>> {
    Json(CORPUS.find(input.phrase.clone()))
}


#[derive(Serialize, Deserialize)]
struct FaceSearchInput {
    features: Vec<f32>,
    id: isize,
    k: isize,
    threshold: f32
}

#[post("/facesearch", format="application/json", data="<input>")]
fn face_search(input: Json<FaceSearchInput>) -> Json<Vec<u64>> {
    let target = if input.id == -1 {
        Target::Exemplar(Array::from_vec(input.features.clone()))
    } else {
        Target::Id(input.id as u64)
    };

    Json(if input.k == -1 {
        FEATURES.tnn(&target, input.threshold)
    } else {
        FEATURES.knn(&target, input.k as usize)
    })
}

fn main() {
    let config = Config::build(Environment::Development)
        .port(8111)
        .workers(1)
        .unwrap();
    rocket::custom(config, true).mount("/", routes![sub_search, face_search]).launch();
}
