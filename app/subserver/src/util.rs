use std::collections::HashMap;
use std::hash::Hash;
use std::time::Instant;
use indicatif::{ProgressBar, ProgressStyle};
use flame;


// Iterator function for taking Vec<(K, V)> -> Map<K, Vec<V>>
pub trait CollectByKey {
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

// HashMap function for merging two hashmaps w/ custom conflict function
pub trait Merge {
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


// Lexically scoped timer
pub struct BlockTimer {
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


// Progress bar for sequential and parallel iterators
macro_rules! progress_iterator_trait {
    ($trait:ident , $struct:ident) => {
        pub trait $trait where Self: Sized {
            fn progress_with(self, progress: ProgressBar) -> $struct<Self>;

            fn progress_count(self, len: usize) -> $struct<Self> {
                let pb = ProgressBar::new(len as u64);
                pb.set_style(
                    ProgressStyle::default_bar()
                        .template("{spinner:.green} [{elapsed_precise}] [{bar:40.cyan/blue}] ({pos}/{len}, ETA {eta})"));
                self.progress_with(pb)
            }

            fn progress(self) -> $struct<Self> {
                self.progress_count(0)
            }
        }
    }
}

progress_iterator_trait! { ProgressIterator, Progress }

pub struct Progress<T> {
    it: T,
    progress: ProgressBar
}

impl<S, T: Iterator<Item=S>> Iterator for Progress<T> {
    type Item = S;

    fn next(&mut self) -> Option<Self::Item> {
        self.progress.inc(1);
        let next = self.it.next();
        if let None = next {
            self.progress.finish();
        }
        next
    }
}

impl<S, T: Iterator<Item=S>> ProgressIterator for T {
    fn progress_with(self, progress: ProgressBar) -> Progress<Self> {
        Progress {
            it: self,
            progress
        }
    }
}


use std::sync::{Arc, Mutex};
use rayon::iter::{ParallelIterator, plumbing::UnindexedConsumer, plumbing::Folder, plumbing::Consumer};
pub struct ParProgress<T> {
    it: T,
    progress: Arc<Mutex<ProgressBar>>
}

progress_iterator_trait! { ParallelProgressIterator, ParProgress }

impl<S: Send, T: ParallelIterator<Item=S>> ParallelProgressIterator for T {
    fn progress_with(self, progress: ProgressBar) -> ParProgress<Self> {
        ParProgress {
            it: self,
            progress: Arc::new(Mutex::new(progress))
        }
    }
}

struct ProgressConsumer<C> {
    base: C,
    progress: Arc<Mutex<ProgressBar>>
}

impl<C> ProgressConsumer<C> {
    fn new(base: C, progress: Arc<Mutex<ProgressBar>>) -> Self {
        ProgressConsumer { base, progress }
    }
}

impl<T, C: Consumer<T>> Consumer<T> for ProgressConsumer<C> {
    type Folder = ProgressFolder<C::Folder>;
    type Reducer = C::Reducer;
    type Result = C::Result;

    fn split_at(self, index: usize) -> (Self, Self, Self::Reducer) {
        let (left, right, reducer) = self.base.split_at(index);
        (ProgressConsumer::new(left, self.progress.clone()),
         ProgressConsumer::new(right, self.progress.clone()),
         reducer)
    }

    fn into_folder(self) -> Self::Folder {
        ProgressFolder {
            base: self.base.into_folder(),
            progress: self.progress.clone()
        }
    }

    fn full(&self) -> bool {
        self.base.full()
    }
}

impl<T, C: UnindexedConsumer<T>> UnindexedConsumer<T> for ProgressConsumer<C> {
    fn split_off_left(&self) -> Self {
        ProgressConsumer::new(self.base.split_off_left(), self.progress.clone())
    }

    fn to_reducer(&self) -> Self::Reducer {
        self.base.to_reducer()
    }
}


struct ProgressFolder<C> {
    base: C,
    progress: Arc<Mutex<ProgressBar>>
}

impl<T, C: Folder<T>> Folder<T> for ProgressFolder<C> {
    type Result = C::Result;

    fn consume(self, item: T) -> Self {
        self.progress.lock().unwrap().inc(1);
        ProgressFolder {
            base: self.base.consume(item),
            progress: self.progress,
        }
    }

    fn complete(self) -> C::Result {
        self.base.complete()
    }

    fn full(&self) -> bool {
        self.base.full()
    }
}


impl<S: Send, T: ParallelIterator<Item=S>> ParallelIterator for ParProgress<T> {
    type Item = S;

    fn drive_unindexed<C: UnindexedConsumer<Self::Item>>(self, consumer: C) -> C::Result {
        let consumer1 = ProgressConsumer::new(consumer, self.progress.clone());
        self.it.drive_unindexed(consumer1)
    }
}



#[allow(dead_code)]
pub struct FlameThreadGuard;

#[allow(dead_code)]
impl FlameThreadGuard {
    pub fn new() -> FlameThreadGuard { FlameThreadGuard }
}

impl Drop for FlameThreadGuard {
    fn drop(&mut self) { flame::commit_thread() }
}
