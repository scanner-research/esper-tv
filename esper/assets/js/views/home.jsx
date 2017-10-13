import React from 'react';
import {observable} from 'mobx';
import {observer} from 'mobx-react';
import SearchResultView from './search_result';
import SearchInputView from './search_input';
import _ from 'lodash';

class SearchResult {
  @observable result = [];
  videos = {};
  frames = {};
  labelers = {};
  labeler_colors = {
    0: 'darkorange',
    1: 'red',
    2: 'cyan',
    3: 'green'
  };
};

@observer
export default class Home extends React.Component {
  state = { clickedBox: null }

  constructor(props) {
    super(props);
    window.search_result = new SearchResult();
  }

  _onSearch = (results) => {
    window.search_result.videos = results.videos;
    window.search_result.frames = results.frames;
    window.search_result.labelers = results.labelers;

    // We have to set clips last, because when we set it that triggers a re-render.
    // If we don't set it last, then the views will see inconsistent state in the search results.
    window.search_result.result = results.result;
  }

  _onBoxClick = (box) => {
    this.setState({clickedBox: box.id});
  }

  render() {
    return (
      <div className='home'>
        <SearchInputView onSearch={this._onSearch} clickedBox={this.state.clickedBox} />
        <SearchResultView />
      </div>
    );
  }
};

/*
 *         <div className='search-results col-md-9'>
 *           <div className='colors'>
 *             {_.keys(this._result.colors).map((name, i) =>
 *               <div key={i}>{name}: <div style={{backgroundColor: this._result.colors[name], width: '10px', height: '10px', display: 'inline-box'}} /></div>
 *             )}
 *           </div>
 *           {orderby_keys.map((key, i) =>
 *             <div className='search-result-video' key={i}>
 *               <div className='group-header'>{key}</div>
 *               <div>
 *                 {this._result.clips[key].map((clip, j) => {
 *                    return <SearchResultView key={j} video={this._result.videos[clip.video_id]} clip={clip} onBoxClick={this._onBoxClick}/>;
 *                  })}
 *               </div>
 *             </div>
 *            )}
 *         </div>
 *       </div>
 * */
