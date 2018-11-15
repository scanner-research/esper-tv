# Installing deps

## caption-index

Probably want to start with step 4 since the files take some time to download.
Also, there is no need to reconfigure or rebuild the containers.
1. pull and then do `git submodule init` and then `git submodule update` in
the esper repo to get the caption index
2. in the app container, navigate into caption-index and run
`pip3 install -r requirements.txt`
3. also in the app container and in the caption-index directory, run
`get_models.sh`
4. in the `app/data directory`, do
`gsutil cp -r gs://esper/tvnews/caption-index10/index10 .`
5. after this, there should be an `index10` directory with some files like
`words.lex`, `docs.bin`, etc...

Note: importing the caption module for the first time takes some time to load the lexicon. <-- may optimize this later to also mmap

## rekall

1. pull and then do `git submodule init` and then `git submodule update` in
the esper repo to get rekall
2. in the app container, navigate into rekall and run
`pip3 install -r requirements.txt`

