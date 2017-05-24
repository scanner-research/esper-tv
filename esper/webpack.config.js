var path = require("path");
var webpack = require('webpack');
var BundleTracker = require('webpack-bundle-tracker');
var ExtractTextPlugin = require('extract-text-webpack-plugin');
var path = require('path');

module.exports = {
  context: __dirname,

  devtool: 'source-map',

  entry: {
    app: './assets/js/index',
  },

  output: {
      path: path.resolve('./assets/bundles/'),
      filename: "[name]-[hash].js"
  },

  plugins: [
    new BundleTracker({filename: './webpack-stats.json'}),
    new ExtractTextPlugin({
      filename: "[name].[contenthash].css",
      disable: process.env.NODE_ENV === "development"
    })
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
      test: /\.(png|woff|woff2|eot|ttf|svg)$/,
      loader: 'url-loader?limit=100000'
    }, {
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
      'models': path.resolve('assets/js/models')
    },
    extensions: ['.js', '.jsx', '.scss', '.css']
  }
};
