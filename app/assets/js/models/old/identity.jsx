import axios from 'axios';
import {observable} from 'mobx';

export class Identity {
  @observable loadedMeta = false;
  @observable loadedFaces = false;

  faces = {};
  ids = {};

  constructor(props) {
    // FIXME: Is the if-else required.
    console.log("in props of Identity");
    this.id = props;
  }

  loadFaces() {
    console.log("in load faces!");
    if (!this.loadedFaces) {
      axios
        .get('/api/id_faces/', {params: {'identity': this.id}})
        .then(((response) => {
          // FIXME: This might stay exactly the same!
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

// CHECK: bind
export class IdentityCollection {
  @observable ids = [];
  constructor () {
    axios
      .get('/api/identities/')
      .then(((response) => {
        let ids = response.data.ids;
        console.log(ids);
        this.ids = ids.map((props) => new Identity(props));
        console.log("created new identity");
      }).bind(this));
  }
}
