import {observable} from 'mobx';

export default class SearchResult {
  @observable result = null;

  labeler_colors = ["#db57b9", "#b9db57", "#57db5f", "#db5784", "#dbc957", "#57b9db", "#57db94", "#c957db", "#5f57db", "#db5f57", "#db9457", "#9457db", "#5784db", "#84db57", "#57dbc9"];
  gender_colors = {'M': '#50c9f8', 'F': '#ff6d86', 'U': '#c0ff00'};

  constructor(results) {
    this.videos = results.videos;
    this.frames = results.frames;
    this.labelers = results.labelers;
    this.dataset = results.dataset;
    this.count = results.count;
    this.type = results.type;
    this.genders = results.genders;
    this.result = results.result;
  }
};
