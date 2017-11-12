import {observable} from 'mobx';

export class Face {
  @observable x1
  @observable y1
  @observable x2
  @observable y2
  @observable track
  @observable cls

  constructor(props) {
    this.x1 = props.bbox.x1;
    this.y1 = props.bbox.y1;
    this.x2 = props.bbox.x2;
    this.y2 = props.bbox.y2;
    this.labeler = props.bbox.labeler;
    this.track = props.track;
    this.cls = props.gender;
  }

  toJSON() {
    return {
      bbox: {
        x1: this.x1,
        y1: this.y1,
        x2: this.x2,
        y2: this.y2,
        labeler: this.labeler,
      },
      track: this.track,
      gender: this.cls
    }
  }
}
