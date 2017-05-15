import axios from 'axios';
import {observable} from 'mobx';

export class Video {
  @observable loadedMeta = false;
  @observable loadedFaces = false;

  faces = [];
  ids = {};

  constructor(props) {
    if (typeof props != "object") {
      this.id = props;
      axios
        .get(`/api/videos/${props}`)
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

  loadFaces() {
    if (!this.loadedFaces) {
      axios
        .get('/api/faces/' + this.id)
        .then(((response) => {
          this.faces = response.data.faces;
          for (var frame in this.faces) {
            this.faces[frame].forEach(((face, i) => {
              let id = face.identity;
              if (id == null) {
                return;
              }
              if (!(id in this.ids)) {
                this.ids[id] = [];
              }
              this.ids[id].push([frame, i]);
            }).bind(this));
          }
          this.loadedFaces = true;
        }).bind(this));
    }
  }
};

export class VideoCollection {
  @observable videos = [];

  constructor () {
    axios
      .get('/api/videos/')
      .then(((response) => {
        let videos = response.data.videos;
        this.videos = videos.map((props) => new Video(props));
      }).bind(this));
  }
}
