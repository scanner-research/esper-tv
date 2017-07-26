import axios from 'axios';
import {observable} from 'mobx';
import {Face} from './face.jsx';

export class Video {
  @observable loadedMeta = false;
  @observable loaded = false;
  loading = false;

  data = {};

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

  loadVideoData() {
    if (!this.loaded && !this.loading) {
      this.loading = true;
      return axios
        .get('/api/frame_and_faces', {params: {'video_id': this.id}})
        .then(((response) => {
          this.data = response.data;
          _.forEach(this.data.frames, (frames, labelset_id) => {
              _.forEach(frames, (set, frame_no) => {
                set.faces = set.faces.map((face) => new Face(face));
              });
          });
          this.loaded = true;
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
