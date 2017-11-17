import React from 'react';
import {observable} from 'mobx';
import {observer} from 'mobx-react';
import SearchResultView from './SearchResultView.jsx';
import SearchInputView from './SearchInputView.jsx';
import _ from 'lodash';

class SearchResult {
  @observable result = null;
  videos = {};
  frames = {};
  labelers = {};
  dataset = '';
  type = '';
  count = 0;
  labeler_colors = {
    0: 'darkorange',
    1: 'red',
    2: 'cyan',
    3: 'green'
  };
};

window.DATASET = observable(SCHEMAS.selected);

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
    window.search_result.dataset = results.dataset;
    window.search_result.count = results.count;
    window.search_result.type = results.type;

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
        {window.search_result.result !== null
         ? (window.search_result.result.length > 0
           ? <SearchResultView />
           : <div>No results matching query.</div>)
         : <div />}
      </div>
    );
  }
};
