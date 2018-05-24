use rayon::prelude::*;
use std::fs::File;
use std::mem;
use std::io::Read;
use ndarray;
use std::fmt::Debug;
use std::io::Cursor;
use byteorder::{ReadBytesExt, LittleEndian};
use std::sync::Mutex;
use block_timer::BlockTimer;
use rand::{thread_rng, sample, Rng};
use rustlearn::prelude::*;
use rustlearn::svm::libsvm::svc::Hyperparameters;
use rustlearn::svm::libsvm::svc::KernelType;


const FEATURE_DIM: usize = 128;

pub type FeatureVec = ndarray::Array<f32, ndarray::Ix1>;

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

        let feature_length = FEATURE_DIM;
        let num_bytes = feature_length * mem::size_of::<f32>();

        let features: Vec<_> = (0..8).collect::<Vec<_>>().par_iter().flat_map(|i| {
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
                features.push(ndarray::Array::from_vec(floatbuf));
            }

            features
        }).collect();
        
        println!("Feature count: {}", features.len());

        let mut file = File::open("/app/.cache/face_ids.bin").expect("cannot open");
        let mut bytebuf = Vec::new();
        file.read_to_end(&mut bytebuf).expect("Failed to read");

        let mut ids = vec![0u64; features.len()];
        let mut rdr = Cursor::new(bytebuf);
        rdr.read_u64_into::<LittleEndian>(&mut ids).unwrap();

        Features {features, ids}
    }

    fn dists(&self, targets: &Vec<&FeatureVec>, non_targets: &Vec<&FeatureVec>, non_target_penalty: f32) -> Vec<(usize, f32)> {
        let mut dists: Vec<_> = self.features.par_iter().map(|f|
            f32::max(0., 
                // Take the min distance to any target
                targets.iter().map(
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
            )
        ).enumerate().collect();
        dists.sort_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap());
        dists
    }

    pub fn knn(&self, target: &Target, k: usize, non_targets: &Vec<Id>, non_target_penalty: f32) -> Vec<(u64,f32)> {
        let targets = match target {
            Target::Exemplar(v) => vec![v],
            Target::Ids(ids) => ids.iter().map(
                |i| &self.features[self.ids.binary_search(&i).unwrap()]
            ).collect()
        };
        let non_targets: Vec<&FeatureVec> = non_targets.iter().map(|i| &self.features[self.ids.binary_search(&i).unwrap()]).collect();
        let dists = self.dists(&targets, &non_targets, non_target_penalty);
        dists.into_iter().take(k).map(|(i, a)| (self.ids[i], a)).collect()
    }

    pub fn tnn(&self, target: &Target, min_t: f32, max_t: f32, non_targets: &Vec<Id>, non_target_penalty: f32) -> Vec<(u64,f32)> {
        let targets = match target {
            Target::Exemplar(v) => vec![v],
            Target::Ids(ids) => ids.iter().map(
                |i| &self.features[self.ids.binary_search(&i).unwrap()]
            ).collect()
        };
        let non_targets: Vec<&FeatureVec> = non_targets.iter().map(|i| &self.features[self.ids.binary_search(&i).unwrap()]).collect();
        let dists = self.dists(&targets, &non_targets, non_target_penalty);
        dists.into_iter().filter(|(_, s)| min_t <= *s && *s <= max_t).map(|(i, a)| (self.ids[i], a)).collect()
    }

    pub fn features_for_id(&self, ids: &Vec<Id>) -> Vec<&FeatureVec> {
        ids.iter().map(|id| &self.features[self.ids.binary_search(&id).unwrap()]).collect()
    }
    
    pub fn svm(&self, pos_ids: &Vec<Id>, neg_ids: &Vec<Id>, n_neg_samples: usize, 
               n_pos_samples: usize, min_t: f32, max_t: f32) -> Vec<(u64,f32)> {
        let pos_features: Vec<&FeatureVec> = pos_ids.iter()
            .map(|i| self.ids.binary_search(&i))
            .filter(|r| r.is_ok())
            .map(|r| &self.features[r.unwrap()])
            .collect();
        let neg_features: Vec<&FeatureVec> = neg_ids.iter()
            .map(|i| self.ids.binary_search(&i))
            .filter(|r| r.is_ok())
            .map(|r| &self.features[r.unwrap()])
            .collect();
        
        // Balance dataset by geting points close to positive examples
        let pos_sample_features: Vec<&FeatureVec> = self.knn(&Target::Ids(pos_ids.clone()), n_pos_samples, neg_ids, 0.25).iter()
            .map(|(i, _)| self.ids.binary_search(&i))
            .filter(|r| r.is_ok())
            .map(|r| &self.features[r.unwrap()])
            .collect();
        
        // Use negative sampling to augment the negative set
        let mut rng = thread_rng();
        let neg_samples = sample(&mut rng, &self.ids, n_neg_samples);
        let neg_sample_features: Vec<&FeatureVec> = neg_samples.iter()
            .map(|i| self.ids.binary_search(&i))
            .filter(|r| r.is_ok())
            .map(|r| &self.features[r.unwrap()])
            .collect();
        
        let n_pos = pos_features.len();
        let n_pos_samples = pos_sample_features.len();
        let n_neg = neg_features.len();
        let n_neg_samples = neg_sample_features.len();
        
        let mut X = Array::zeros(n_pos + n_pos_samples + n_neg + n_neg_samples, FEATURE_DIM);
        let mut y = Array::ones(n_pos + n_pos_samples + n_neg + n_neg_samples, 1);
        for i in 0..n_pos {
            y.set(i, 0, 0.);
            for j in 0..FEATURE_DIM {
                X.set(i, j, pos_features[i][j]);
            }
        }
        for i in 0..n_pos_samples {
            y.set(i + n_pos, 0, 0.);
            for j in 0..FEATURE_DIM {
                X.set(i + n_pos, j, pos_sample_features[i][j]);
            }
        }
        for i in 0..n_neg {
            for j in 0..FEATURE_DIM {
                X.set(i + n_pos + n_pos_samples, j, neg_features[i][j]);
            }
        }
        for i in 0..n_neg_samples {
            for j in 0..FEATURE_DIM {
                X.set(i + n_pos + n_pos_samples + n_neg, j, neg_sample_features[i][j]);
            }
        }
        
        // Shuffle the dataset
        let mut shuffled_idxs: Vec<usize> = Vec::with_capacity(X.rows());
        for i in 0..X.rows() {
            shuffled_idxs.push(i as usize);
        }
        rng.shuffle(&mut shuffled_idxs);
        X = X.get_rows(&shuffled_idxs);
        y = y.get_rows(&shuffled_idxs);
        
        let mut model = Hyperparameters::new(X.cols(), KernelType::Linear, 2)
                                            .C(0.3)
                                            .build();

        model.fit(&X, &y).expect("Failed to fit");
        
        let mut labels: Vec<_> = self.features.par_iter().map(
            |f| {
                let mut x = Array::zeros(1, FEATURE_DIM);
                for i in 0..FEATURE_DIM {
                    x.set(0, i, f[i]);
                }
                model.decision_function(&x).expect("Failed to predict").get(0, 0) as f32
            }
        ).enumerate().collect();
        labels.sort_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap());
        labels.par_iter()
              .filter(|(_, s)| min_t <= *s && *s <= max_t)
              .map(|(i, a)| (*&self.ids[*i], *a))
              .collect()
    }
}
