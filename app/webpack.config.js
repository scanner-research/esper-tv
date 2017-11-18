var path = require("path");
var BundleTracker = require('webpack-bundle-tracker');
var ExtractTextPlugin = require('extract-text-webpack-plugin');

module.exports = {
  context: __dirname,

  // Include source maps for all compiled files
  devtool: 'source-map',

  // Start looking for files beginning at these entrypoints
  entry: {
    app: './assets/js/index',
    styles: './assets/css/main'
  },

  // Put all output files at assets/bundles
  output: {
      path: path.resolve('./assets/bundles/'),
      filename: "[name].js"
  },

  plugins: [
    // BundleTracker lets Django know about the webpack build status, displaying errors if they occur
    new BundleTracker({filename: './assets/bundles/webpack-stats.json'}),

    // ExtractTextPlugin allows us to separate CSS output files from JS.
    // See: https://github.com/webpack-contrib/extract-text-webpack-plugin
    new ExtractTextPlugin("[name].css"),
  ],

  module: {
    rules: [{
      test: /\.scss$/,
      use: ExtractTextPlugin.extract({
        use: [{
          loader: "css-loader"
        }, {
          loader: "sass-loader"
        }]
      })
    }, {
      test: /\.css$/,
      use: ExtractTextPlugin.extract({
        use: [{
          loader: "css-loader"
        }]
      })
    }, {
      // Stops Bootstrap from complaining
      test: /\.(png|woff|woff2|eot|ttf|svg)$/,
      loader: 'url-loader?limit=100000'
    }, {
      // Compile JSX files to JS
      test: /\.jsx?$/,
      exclude: /node_modules/,
      use: [{
        loader: 'babel-loader',
        options: {
          plugins: ['transform-decorators-legacy'],
          presets: ['stage-0', 'react']
        }
      }]
    }]
  },

  // TODO: generic way to resolve aliases?
  resolve: {
    modules: ['node_modules', 'assets'],
    alias: {
      'views': path.resolve('assets/js/views'),
      'models': path.resolve('assets/js/models'),
      'utils': path.resolve('assets/js/utils.jsx'),
    },
    extensions: ['.js', '.jsx', '.scss', '.css']
  }
};
