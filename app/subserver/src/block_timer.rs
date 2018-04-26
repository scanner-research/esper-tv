use std::time::Instant;

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
