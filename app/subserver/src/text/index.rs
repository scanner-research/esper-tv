use datatypes::Document;
use suffix::SuffixTable;
use std::collections::HashMap;

fn ngrams(words: Vec<&str>, query: &str) -> Vec<usize> {
    let parts = query.split(" ").collect::<Vec<_>>();
    words.windows(parts.len()).enumerate().filter(|(_, window)| {
        parts.iter().zip(window.iter()).all(|(i, j)| i == j)
    }).map(|(i, _)| i).collect::<Vec<_>>()
}

pub trait Indexed: Send + Sync {
    fn new(s: String) -> Self;

    fn positions_char(&self, query: &str) -> Vec<usize>;

    fn positions_word(&self, query: &str, meta: &Document) -> Vec<usize> {
        let pos = self.positions_char(query);

        let word_index =
            meta.words.iter().enumerate().map(|(i, w)| (w.char_start as usize, i)).collect::<HashMap<_,_>>();

        pos.into_iter().filter_map(|i| word_index.get(&i)).cloned().collect::<Vec<_>>()
    }
}


pub struct IndexedTable {
    table: SuffixTable<'static, 'static>
}

impl Indexed for IndexedTable {
    fn new(s: String) -> Self {
        IndexedTable {
            table: SuffixTable::new(s)
        }
    }

    fn positions_char(&self, query: &str) -> Vec<usize> {
        let mut v = Vec::new();
        v.extend_from_slice(&self.table.positions(query).into_iter().map(|i| *i as usize).collect::<Vec<_>>());
        v
    }
}

pub struct LinearSearch {
    text: String
}

impl Indexed for LinearSearch {
    fn new(s: String) -> Self { LinearSearch { text: s } }

    fn positions_char(&self, _query: &str) -> Vec<usize> {
        unreachable!()
    }

    fn positions_word(&self, query: &str, meta: &Document) -> Vec<usize> {
        ngrams(meta.words.iter().map(|w| w.on_slice(&self.text)).collect::<Vec<_>>(), query)
    }
}
