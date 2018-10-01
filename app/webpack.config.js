"use strict";

const path = require('path');
const BundleTracker = require('webpack-bundle-tracker');
const ExtractTextPlugin = require('extract-text-webpack-plugin');
const webpack = require('webpack');

module.exports = {
  entry: {
    web: './assets/js/web',
    styles: './assets/css/main',
  },

  context: __dirname,

  // Include source maps for all compiled files
  devtool: 'source-map',

  // Put all output files at assets/bundles
  output: {
    path: path.resolve('./assets/bundles/'),
    filename: "[name].js",
  },

  plugins: [
    // BundleTracker lets Django know about the webpack build status, displaying errors if
    // they occur
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
      test: /\.(png|woff|woff2|eot|ttf|svg|otf)$/,
      loader: 'url-loader?limit=100000'
    }, {
      // Compile JSX files to JS
      test: /\.jsx?$/,
      exclude: /node_modules/,
      use: [{
        loader: 'babel-loader',
        options: {
          plugins: ['transform-decorators-legacy'],
          presets: ['env', 'stage-0', 'react']
        }
      }]
    }, {
      test: /\.js$/,
      use: ["source-map-loader"],
      enforce: "pre"
    }]
  },

  // TODO: generic way to resolve aliases?
  resolve: {
    symlinks: false, // https://github.com/npm/npm/issues/5875
    modules: ['node_modules', 'assets'],
    extensions: ['.js', '.jsx', '.scss', '.css']
  }
};
