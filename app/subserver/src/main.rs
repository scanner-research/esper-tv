#![feature(proc_macro, specialization, plugin)]
#![plugin(rocket_codegen)]

extern crate serde;
#[macro_use] extern crate serde_derive;
#[macro_use] extern crate lazy_static;
extern crate serde_json;
extern crate glob;
extern crate rayon;
extern crate srtparse;
extern crate suffix;
extern crate indicatif;
#[macro_use] extern crate rocket;
extern crate ndarray;
extern crate byteorder;
#[macro_use] extern crate nom;
extern crate rand;
extern crate rustlearn;

use rocket::config::{Config, Environment};
use glob::glob;
use std::collections::HashMap;
use ndarray::Array;

use block_timer::BlockTimer;
use corpus::Corpus;
use knn::{Features, Target};
use progress::ProgressIterator;
use json::Json;

mod knn;
mod corpus;
mod block_timer;
mod progress;
mod json;

lazy_static! {
    static ref CORPUS: Corpus<corpus::IndexedTable>  = {
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
    phrases: Vec<String>
}

#[post("/subsearch", format="application/json", data="<input>")]
fn sub_search(input: Json<SubSearchInput>) -> Json<Vec<HashMap<String, Vec<(f64, f64)>>>> {
    Json(input.phrases.iter().cloned().map(|phrase| CORPUS.find(phrase)).collect())
}


#[post("/subcount", format="application/json", data="<input>")]
fn sub_count(input: Json<SubSearchInput>) -> Json<Vec<u64>> {
    Json(input.phrases.iter().progress().cloned().map(|phrase| CORPUS.count(phrase)).collect())
}


#[derive(Serialize, Deserialize)]
struct FaceSearchInput {
    features: Vec<f32>,
    ids: Vec<u64>,
    k: isize,
    min_threshold: f32,
    max_threshold: f32,
    non_targets: Vec<u64>,
    non_target_penalty: f32
}

#[post("/facesearch", format="application/json", data="<input>")]
fn face_search(input: Json<FaceSearchInput>) -> Json<Vec<(u64,f32)>> {
    let target = if input.ids.is_empty() {
        Target::Exemplar(Array::from_vec(input.features.clone()))
    } else {
        Target::Ids(input.ids.iter().map(|i| *i as knn::Id).collect())
    };
    let non_targets: Vec<knn::Id> = input.non_targets.iter().map(|i| *i as knn::Id).collect();
    
    Json(if input.k == -1 {
        FEATURES.tnn(&target, input.min_threshold, input.max_threshold, &non_targets, input.non_target_penalty)
    } else {
        FEATURES.knn(&target, input.k as usize, &non_targets, input.non_target_penalty)
    })
}

#[derive(Serialize, Deserialize)]
struct FaceSearchSVMInput {
    pos_ids: Vec<u64>,
    neg_ids: Vec<u64>,
    min_threshold: f32,
    max_threshold: f32,
    neg_samples: usize,
    pos_samples: usize
}

#[post("/facesearch_svm", format="application/json", data="<input>")]
fn face_search_svm(input: Json<FaceSearchSVMInput>) -> Json<Vec<(u64,f32)>> {
    let pos_ids = input.pos_ids.iter().map(|i| *i as knn::Id).collect();
    let neg_ids = input.neg_ids.iter().map(|i| *i as knn::Id).collect();
    Json(FEATURES.svm(&pos_ids, &neg_ids, input.neg_samples, input.pos_samples,
                      input.min_threshold, input.max_threshold))
}

#[derive(Serialize, Deserialize)]
struct FaceFeaturesInput {
    ids: Vec<knn::Id>,
}

#[post("/facefeatures", format="application/json", data="<input>")]
fn face_features(input: Json<FaceFeaturesInput>) -> Json<Vec<Vec<f32>>> {
    Json(FEATURES.features_for_id(&input.ids).into_iter().map(|v| v.to_vec()).collect())
}

fn main() {
    let config = Config::build(Environment::Development)
        .port(8111)
        .workers(1)
        .unwrap();
    rocket::custom(config, true).mount("/", routes![sub_search, sub_count, face_search, face_search_svm, face_features]).launch();
}
