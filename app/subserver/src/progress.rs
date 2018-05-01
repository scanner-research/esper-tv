use indicatif::ProgressBar;

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

pub trait ProgressIterator where Self: Sized {
    fn progress_with(self, progress: ProgressBar) -> Progress<Self>;

    fn progress_count(self, len: u64) -> Progress<Self> {
        self.progress_with(ProgressBar::new(len))
    }

    fn progress(self) -> Progress<Self> {
        self.progress_count(0)
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
