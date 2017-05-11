import axios from 'axios';
import {observable} from 'mobx';

export class Video {
  @observable faces = []

  constructor(props) {
    for (var k in props) {
      this[k] = props[k];
    }
  }

  loadFaces() {
    axios
      .get('/api/faces/' + this.id)
      .then(((response) => {
        this.faces = response.data.faces;
        console.log(this.faces);
      }).bind(this));
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
