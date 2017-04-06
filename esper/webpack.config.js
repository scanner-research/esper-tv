var path = require("path");
var webpack = require('webpack');
var BundleTracker = require('webpack-bundle-tracker');
var ExtractTextPlugin = require('extract-text-webpack-plugin');

module.exports = {
  context: __dirname,

  devtool: 'source-map',

  entry: {
    app: './assets/js/index',
    vendor: ['react', 'react-dom']
  },

  output: {
      path: path.resolve('./assets/bundles/'),
      filename: "[name]-[hash].js"
  },

  plugins: [
    new BundleTracker({filename: './webpack-stats.json'}),
    new webpack.optimize.CommonsChunkPlugin({
      names: ['vendor'],
      filename: 'vendor.js',
      minChunks: Infinity
    }),
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
          presets: ['react']
        }
      }]
    }]
  },

  resolve: {
    modules: ['node_modules', 'assets'],
    extensions: ['.js', '.jsx', '.scss', '.css']
  }
};
