# Developing Esper

If you're developing features for Esper, first talk to [Will](mailto:wcrichto@cs.stanford.edu) and join our [cmugraphics.slack.com](Slack channel).


## Frontend

While editing the SASS or JSX files, use the Webpack watcher:
```
dc exec app npm run watch
```

This will automatically rebuild all the frontend files into `assets/bundles` when you change a relevant file.

> Note: the watching functionality appears to be broken on OS X, so you'll want to dev on a Linux box. I don't think this is fixable. [See this issue](https://github.com/rails/rails/issues/25186).
