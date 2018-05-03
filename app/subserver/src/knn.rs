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

pub struct Features {
    features: Vec<FeatureVec>,
    ids: Vec<u64>
}

pub enum Target {
    Id(u64),
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

    fn dists(&self, target: &FeatureVec) -> Vec<(usize, f32)> {
        let mut dists: Vec<_> = self.features.par_iter().map(|f| (target - f).mapv(|i| i.powi(2)).scalar_sum())
            .enumerate().collect();
        dists.sort_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap());
        dists
    }

    pub fn knn(&self, target: &Target, k: usize) -> Vec<u64> {
        let target = match target {
            Target::Exemplar(v) => v,
            Target::Id(i) => &self.features[self.ids.binary_search(&i).unwrap()]
        };
        let dists = self.dists(target);
        dists.into_iter().take(k).map(|(i, _)| &self.ids[i]).cloned().collect()
    }

    pub fn tnn(&self, target: &Target, min_t: f32, max_t: f32) -> Vec<u64> {
        let target = match target {
            Target::Exemplar(v) => v,
            Target::Id(i) => &self.features[self.ids.binary_search(&i).unwrap()]
        };
        let dists = self.dists(target);
        dists.into_iter().filter(|(_, s)| *s >= min_t && *s <= max_t).map(|(i, _)| &self.ids[i]).cloned().collect()
    }
}
