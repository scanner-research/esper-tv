use rayon::prelude::*;
use std::fs::File;
use std::mem;
use std::io::Read;
use ndarray::{Array, Ix1};
use std::fmt::Debug;
use std::io::Cursor;
use byteorder::{ReadBytesExt, LittleEndian};
use std::sync::Mutex;
use block_timer::BlockTimer;

pub type FeatureVec = Array<f32, Ix1>;

pub type Id = u64;

pub struct Features {
    features: Vec<FeatureVec>,
    ids: Vec<Id>
}

pub enum Target {
    Ids(Vec<Id>),
    Exemplar(FeatureVec)
}

impl Features {
    pub fn new() -> Features {
        let _timer = BlockTimer::new("Feature read");

        let feature_length = 128;
        let num_bytes = feature_length * mem::size_of::<f32>();

        let features: Vec<_> = (0..1).collect::<Vec<_>>().par_iter().flat_map(|i| {
            let path = format!("/app/.cache/all_embs_flat_{}.bin", i);
            let mut file = File::open(path).expect("cannot open");
            let mut bytebuf = Vec::new();
            file.read_to_end(&mut bytebuf).expect("Failed to read");

            let mut features = Vec::new();

            for i in 0..bytebuf.len()/num_bytes {
                let mut floatbuf = vec![0.0f32; feature_length];
                let start = i*num_bytes;
                let mut rdr = Cursor::new(&bytebuf[start..start+num_bytes]);
                rdr.read_f32_into::<LittleEndian>(&mut floatbuf).unwrap();
                features.push(Array::from_vec(floatbuf));
            }

            features
        }).collect();

        let mut file = File::open("/app/.cache/face_ids.bin").expect("cannot open");
        let mut bytebuf = Vec::new();
        file.read_to_end(&mut bytebuf).expect("Failed to read");

        let mut ids = vec![0u64; features.len()];
        let mut rdr = Cursor::new(bytebuf);
        rdr.read_u64_into::<LittleEndian>(&mut ids).unwrap();

        Features {features, ids}
    }

    fn dists(&self, targets: &Vec<&FeatureVec>, non_targets: &Vec<&FeatureVec>, non_target_penalty: f32) -> Vec<(usize, f32)> {
        let mut dists: Vec<_> = self.features.par_iter().map(
            // Take the min distance to any target
            |f| targets.iter().map(
                |t| (*t - f).mapv(|i| i.powi(2)).scalar_sum().sqrt()
            ).fold(1./0., f32::min) 
            - 
            // Subtract the min distance to any non-target
            if non_targets.is_empty() { 
                0. 
            } else { 
                non_target_penalty * non_targets.iter().map(
                    |g| (*g - f).mapv(|i| i.powi(2)).scalar_sum().sqrt()
                ).fold(1./0., f32::min)
            }
        ).enumerate().collect();
        dists.sort_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap());
        dists
    }

    pub fn knn(&self, target: &Target, k: usize, non_targets: &Vec<Id>, non_target_penalty: f32) -> Vec<u64> {
        let targets = match target {
            Target::Exemplar(v) => vec![v],
            Target::Ids(ids) => ids.iter().map(
                |i| &self.features[self.ids.binary_search(&i).unwrap()]
            ).collect()
        };
        let non_targets: Vec<&FeatureVec> = non_targets.iter().map(|i| &self.features[self.ids.binary_search(&i).unwrap()]).collect();
        let dists = self.dists(&targets, &non_targets, non_target_penalty);
        dists.into_iter().take(k).map(|(i, _)| &self.ids[i]).cloned().collect()
    }

    pub fn tnn(&self, target: &Target, min_t: f32, max_t: f32, non_targets: &Vec<Id>, non_target_penalty: f32) -> Vec<u64> {
       let targets = match target {
            Target::Exemplar(v) => vec![v],
            Target::Ids(ids) => ids.iter().map(
                |i| &self.features[self.ids.binary_search(&i).unwrap()]
            ).collect()
        };
        let non_targets: Vec<&FeatureVec> = non_targets.iter().map(|i| &self.features[self.ids.binary_search(&i).unwrap()]).collect();
        let dists = self.dists(&targets, &non_targets, non_target_penalty);
        dists.into_iter().filter(|(_, s)| min_t <= *s && *s <= max_t).map(|(i, _)| &self.ids[i]).cloned().collect()
    }

    pub fn features_for_id(&self, ids: &Vec<Id>) -> Vec<&FeatureVec> {
        ids.iter().map(|id| &self.features[self.ids.binary_search(&id).unwrap()]).collect()
    }
}
