import {observable} from 'mobx';

export default class SearchResult {
  @observable result = null;

  gender_colors = {'M': '#50c9f8', 'F': '#ff6d86', 'U': '#c0ff00'};

  constructor(results) {
    this.videos = results.videos;
    this.frames = results.frames;
    this.labelers = results.labelers;
    this.count = results.count;
    this.type = results.type;
    this.genders = results.genders;
    this.result = results.result;
  }
};
