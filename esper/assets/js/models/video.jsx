import axios from 'axios';
import {observable} from 'mobx';
import {Face} from './face.jsx';

export class Video {
  @observable loadedMeta = false;
  @observable loadedFaces = false;
  @observable loadedFrames = false;
  loadingFaces = false;
  loadingFrames = false;

  faces = {};
  ids = {};
  frames = {}

  constructor(props) {
    if (typeof props != "object") {
      this.id = props;
      axios
        .get('/api/videos', {params: {'id': this.id}})
        .then(((response) => {
          let video = response.data.videos[0];
          this._setProps(video);
        }).bind(this));
    } else {
      this._setProps(props);
    }
  }

  _setProps(props) {
    this.id = props.id;
    for (var k in props) {
      this[k] = props[k];
    }
    this.loadedMeta = true;
  }

  loadFrames() {
    if (!this.loadedFrames && !this.loadingFrames) {
      this.loadingFrames = true;
      return axios
        .get('/api/frames', {params: {
          'video_id': this.id, 'handlabeled': true}})
        .then(((response) => {
          response.data.frames.forEach(((frame) => {
            this.frames[frame.number] = frame;
          }).bind(this));
          this.loadedFrames = true;
          return true;
        }).bind(this));
    } else {
      return new Promise((resolve, _) => resolve(false));
    }
  }

  loadFaces() {
    if (!this.loadedFaces && !this.loadingFaces) {
      this.loadingFaces = true;
      return axios
        .get('/api/faces', {params: {'video_id': this.id}})
        .then(((response) => {
          this.faces = _.mapValues(response.data.faces, (frames) =>
            _.mapValues(frames, (frame) =>
              frame.map((face) => new Face(face))));
          this.loadedFaces = true;
          return true;
        }).bind(this));
    } else {
      return new Promise((resolve, _) => resolve(false));
    }
  }
};

export class VideoCollection {
  @observable videos = [];

  constructor () {
    axios
      .get('/api/videos')
      .then(((response) => {
        let videos = response.data.videos;
        this.videos = videos.map((props) => new Video(props));
      }).bind(this));
  }
}
