import React from 'react';
import {observable} from 'mobx';
import {observer} from 'mobx-react';
import SearchResultView from './search_result';
import SearchInput from './search_input';
import _ from 'lodash';

class SearchResult {
  @observable clips = {};
  videos = {};
  colors = {};
};

@observer
export default class Home extends React.Component {
  constructor(props) {
    super(props);
    this._result = new SearchResult();
  }

  _onSearch = (results) => {
    this._result.videos = results.videos;
    this._result.colors = results.colors;
    window.COLORS = results.colors;
    // We have to set clips last, because when we set it that triggers a re-render.
    // If we don't set it last, then the views will see inconsistent state in the search results.
    this._result.clips = results.clips;
  }

  render() {
    let orderby_keys = _.keys(this._result.clips);
    orderby_keys.sort();

    return (
      <div className='row'>
        <div className='col-md-3'>
          <SearchInput result={this._result} onSearch={this._onSearch} />
        </div>
        <div className='search-results col-md-9'>
          <div className='colors'>
            {_.keys(this._result.colors).map((name, i) =>
              <div key={i}>{name}: <div style={{backgroundColor: this._result.colors[name], width: '10px', height: '10px', display: 'inline-box'}} /></div>
            )}
          </div>
          {orderby_keys.map((key, i) =>
            <div className='search-result-video' key={i}>
              <div>{key}</div>
              <div>
                {this._result.clips[key].map((clip, j) => {
                   return <SearchResultView key={j} video={this._result.videos[clip.video_id]} clip={clip} />;
                 })}
              </div>
            </div>
           )}
        </div>
      </div>
    );
  }

};
