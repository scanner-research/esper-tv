"use strict";

var path = require('path');
var BundleTracker = require('webpack-bundle-tracker');
var ExtractTextPlugin = require('extract-text-webpack-plugin');
var webpack = require('webpack');
var _ = require('lodash');

module.exports = env => {
  var baseConfig = {
    context: __dirname,

    // Include source maps for all compiled files
    devtool: 'source-map',

    // Put all output files at assets/bundles
    output: {
      path: path.resolve('./assets/bundles/'),
      filename: "[name].js",
    },

    plugins: [
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
            presets: ['env', 'stage-0', 'react']
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
        'utils': path.resolve('assets/js/utils'),
      },
      extensions: ['.js', '.jsx', '.scss', '.css']
    }
  };

  var webConfig = _.cloneDeep(baseConfig);
  webConfig.entry = {
    web: './assets/js/web',
    styles: './assets/css/main',
    bootstrap: './assets/css/bootstrap',
  };
  // BundleTracker lets Django know about the webpack build status, displaying errors if they occur
  webConfig.plugins.unshift(new BundleTracker({filename: './assets/bundles/webpack-stats.json'}));

  // Jupyter extensions have to be AMD-compatible since Jupyter uses require.js as module system.
  var jupyterConfig = _.cloneDeep(baseConfig);
  jupyterConfig.output.libraryTarget = 'amd';
  jupyterConfig.entry = {
    extension: './assets/js/extension',
    jupyter: './assets/js/jupyter',
    styles: './assets/css/main',
    bootstrap: './assets/css/bootstrap',
  };

  if (env === undefined || !("target" in env)) {
    return [webConfig, jupyterConfig];
  } else if (env.target == 'jupyter') {
    return jupyterConfig;
  } else if (env.target == 'web') {
    return webConfig;
  } else {
    throw "Invalid target";
  }
}
