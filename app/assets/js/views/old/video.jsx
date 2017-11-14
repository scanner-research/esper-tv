import React from 'react';
import mobx from 'mobx';
import _ from 'lodash';
import leftPad from 'left-pad';
import axios from 'axios';
import {observer} from 'mobx-react';
import {Button, Collapse, Pagination} from 'react-bootstrap';

import * as models from 'models/mod.jsx';
import VideoSummary from './video_summary.jsx';
import {Box, BoundingBoxView, boundingRect} from './bbox.jsx';

// TODO(wcrichto): make this dynamic
let AUTOLABELED = 1;
let HANDLABELED = 2;

@observer
class VideoView extends React.Component {
  constructor(...args) {
    super(...args);
    this.state = {
      showAllFaces: false,
      frame: 0,
      labelMode: true,
      curTrack: null,
      lastTrackBox: -1,
      segStart: -1,
      segEnd: -1,
      activePage: this.props.page - 1 
    };
    this._trackCounter = -1;
    document.addEventListener('keydown', this._onKeyDown);
  }

  _renderVideoSummary() {
    let video = this.props.store;
    let table = [
      ['ID', video.id],
      ['Path', video.path],
      ['# frames', video.num_frames],
      ['FPS', video.fps],
      ['Resolution', `${video.width}x${video.height}`]];

    return (
      <div className="video-meta">
        <VideoSummary store={video} frame={this.state.frame} show_meta={false} />
        <h2>Metadata</h2>
        <table className="table">
          <tbody>
            {table.map((pair, i) =>
              <tr key={i}><td>{pair[0]}</td><td>{pair[1]}</td></tr>
             )}
          </tbody>
        </table>
        <Button onClick={() => this.setState({labelMode: !this.state.labelMode})}>
          {this.state.labelMode ? 'View mode' : 'Label mode'}
        </Button>
        {this.state.labelMode
         ? <div>
           <br />
           <div>Current track: {this.state.curTrack || 'none'}</div>
           <br />
           <u>Segment Labels</u>
           <ul>
             <li> 0 - Clear Labels </li>
             {_.map(video.data.labels, (label, id) => 
               <li key={id}> {id} - {label} </li>
              )}
           </ul>

           <u>Instructions</u>
           <ul>
             <li><b>Click/drag image</b> - make new box</li>
             <li><b>Click/drag box</b> - move box around</li>
             <li><b>space bar</b> - change gender</li>
             <li><b>d</b> - delete box</li>
             <li><b>t</b> - manage tracks</li>
             <li><b>s</b> - select sequence of frames</li>
             <li><b>a</b> - mark selected sequence as accepted</li>
             <li><b>f</b> - blow-up a frame</li>
             <li><b>c</b> - clear track/frame selection</li>
             <li><b>q</b> - set all boxes with track to selected track</li>
             <li><b>u</b> - remove all boxes with the same track</li>
           </ul>
         </div>
        : <div />}
      </div>
    );
  }

  _renderFace(face, j) {
    return <img key={j} src={`/static/thumbnails/${face.labelset}_${face.id}.jpg`}
                className={`gender-${face.gender}`} />;
  }

  _renderFaces() {
    let video = this.props.store;
    return (
      <div className="video-faces">
        {video.loadedFaces
         ? (<div>
           <div className="cluster">
             <h3>All faces
               &nbsp;
               <Button onClick={() => this.setState({showAllFaces: !this.state.showAllFaces})}>
                 +
               </Button>
             </h3>
             <Collapse in={this.state.showAllFaces}>
               <div>
                 {_.map(video.faces, (faces, i) =>
                   <div className="frame" key={i}>
                     {faces.map(this._renderFace)}
                   </div>)}
               </div>
             </Collapse>
           </div>
           <div className="clusters">
             {_.map(video.ids, (faces, i) =>
               <div className='cluster' key={i}>
                 <h3>Cluster {i}</h3>
                 {faces.map((entry, j) => {
                    let [frame, face_index] = entry;
                    let frame_faces = video.faces[frame];
                    let face = frame_faces[face_index];
                    return this._renderFace(face, j);
                  })}
               </div>
              )}
           </div>
         </div>)
         : (<div>Loading faces...</div>)}
      </div>
    );
  }

  _onFacesLoaded(wasLoaded) {
    if (!wasLoaded) { return; }
    let video = this.props.store;
    if (!video.loaded) { return; }
    this._frames = {};
    this._allUnlabeledFaces = [];
    _.forEach(video.data.frames, (frames, labelset) => {
      this._frames[labelset] = {};
      _.forEach(frames, (frame_data, frame) => {
        this._frames[labelset][frame] = frame_data; 
        this._allUnlabeledFaces = this._allUnlabeledFaces.concat(this._frames[labelset][frame].faces);
      });
    });
    this.forceUpdate();
  }

  _onChange = (box) => {
    let i = this._allUnlabeledFaces.indexOf(box);
	if (i == -1) { this._allUnlabeledFaces.push(box);}
    if (box.track == null) { return; }
    this._allUnlabeledFaces.forEach((other_box) => {
      if (box.track == other_box.track) {
        other_box.cls = box.cls;
      }
    });
  }

  _onTrack = (box) => {
    let i = this._allUnlabeledFaces.indexOf(box);
	if (i == -1) { this._allUnlabeledFaces.push(box);}
    if (this.state.curTrack == null) {
      console.log('Creating track');
      let track = box.track;
      if (track == null) {
        box.track = this._trackCounter;
        track = box.track;
        this._trackCounter--;
      }
      this.setState({curTrack: track, lastTrackBox: i});
    } else {
      console.log('Adding to track')
      box.track = this.state.curTrack;
      this.setState({lastTrackBox: i});
    }
  }

  //set all boxes with the same track to the current track
  _onSetTrack = (box) => {
	let i = this._allUnlabeledFaces.indexOf(box);
	if (i == -1) { this._allUnlabeledFaces.push(box);}
	if (this.state.curTrack == null || box.track == null) {return;}
	let track_to_set = box.track;
	this._allUnlabeledFaces.forEach((other_box) => {
	  if(other_box.track == track_to_set){
		other_box.track = this.state.curTrack; 
	  }
	});
  }

  _onDeleteTrack = (box) => {
    if (box.track == null) {return;}
    let track_to_remove = box.track;
    _.forEach(this._faces, (labelset, labelset_id) => {
      _.forEach(labelset, (face_list, frame_id) => {
        let remove_indexes = []
        face_list.forEach((frame, ni) => {
          if (frame.track == track_to_remove) {
            remove_indexes.push(ni);
          }
        });
        remove_indexes.sort()
        for (let i = remove_indexes.length -1; i >= 0; --i){
          face_list.splice(remove_indexes[i], 1);
        }

      });
    });
    this.setState({lastTrackBox : -1, curTrack : null});
  }

  _onKeyDown = (e) => {
    let chr = String.fromCharCode(e.which);
    // Clear track, first accepted frame
    if (chr == "C") {
      this.setState({
        curTrack : null,
        segStart : -1,
        segEnd : -1,
        lastTrackBox : -1
      });
    }else if (chr == 'A'){
      this._onAccept();
    }else if (chr >= '0' && chr <= '9'){
      this._onSetFrameLabel(Number(chr))
    }
  }

  _onSetFrameLabel = (n) => {
    let video = this.props.store;
    if (this.state.segStart >= 0 && this.state.segEnd > this.state.segStart && 
            (n==0 || n in video.data.labels)) {
      for (var i = this.state.segStart; i <= this.state.segEnd; ++i) {
        let idx = i * video.stride;
        let frame = this._getFrameData(idx);
        if (n == 0){
          frame.labels = [];
        }else if (frame.labels.indexOf(n)==-1) {
          frame.labels.push(n);
          frame.labels.sort()
        }
      }
      this.forceUpdate();
    }
  }

  _onSelect = (ni) => {
    if (this.state.segStart < 0){
      this.setState({segStart: ni});
    }else if (ni > this.state.segStart){
      this.setState({segEnd: ni});
    }
  }

  _onAccept = () => {
    if (this.state.segStart >= 0 && this.state.segEnd > this.state.segStart) {
      let video = this.props.store;
      let data = {frames: {}, video: this.props.store.id};
      let sent = {}
      for (var i = this.state.segStart; i <= this.state.segEnd; ++i) {
        let idx = i * video.stride;
        let labeled_frame = this._getFrameData(idx)
        let faces = labeled_frame.faces.map((face) => face.toJSON());
        sent[idx] = labeled_frame;
        data.frames[idx] = {'faces':faces, 'labels':labeled_frame.labels};
      }

      axios
        .post('/api/handlabeled', data)
        .then((resp) => {
          _.forEach(sent, (data, key) => {
            this._frames[HANDLABELED][key] = data
          });
          this.setState({segStart: -1,
                         segEnd: -1});
          // do something with response?
        }).catch((err) => {
          alert("Server failed to process labels: "+err);
        });
    }
  }

  _handlePaginationSelect = (selectedPage) => {
      this.setState({
          activePage: selectedPage-1
      });

    window.history.replaceState(window.history.state,'', '/video/'+this.props.store.id+'/'+selectedPage)

  }
  _getFrameData = (n) => {
     let video = this.props.store;
     let ret = {}
     let labelset_id = n in this._frames[2] ? 2 : 1;
     if (n in this._frames[labelset_id]) {
       ret = this._frames[labelset_id][n];
     } else{
       this._frames[labelset_id][n] = {'faces':[], 'labels':[]};
       ret = this._frames[labelset_id][n];
     }
     return ret;
  }
  
  _getFacesForFrame = (n) => {
    return this._getFrameData(n).faces;
  }

  _renderLabeler() {
    let video = this.props.store;

    if (!video.loaded || !this._frames) {
      return <div>Loading faces...</div>;
    }

    const stride = video.stride;
    // TODO: doing something generic here (passing a list of items)
    // is challenging becaues of the way bounding boxes are drawn
    // I will revisit this when this is set in stone
    const framesPerPage = 200;
    const totalPages = Math.ceil(video.num_frames/(stride*framesPerPage));
    const activePage = this.state.activePage;
    const firstFrame = activePage*framesPerPage*stride;
    const lastFrame = Math.min(firstFrame+(framesPerPage*stride), video.num_frames);

    return (
      <div className='video-labeler'>
      <div>
      <Pagination prev next first last ellipsis boundaryLinks maxButtons={10}
      activePage={activePage+1} items={totalPages} onSelect={this._handlePaginationSelect}/>
      </div>
      {_.range(firstFrame, lastFrame, stride).map((n) => {
         let ni = n / stride;
         let path = `/static/thumbnails/${video.id}_frame_${leftPad(n+1, 6, '0')}.jpg`;
         let selected = this.state.segStart == ni || (this.state.segStart <= ni &&  ni <= this.state.segEnd);
         let accepted = n in this._frames[HANDLABELED];
         let selectedCls = selected ? 'selected' : '';
         let acceptedCls = accepted ? 'accepted' : '';
         let cls = `bounding-box-wrapper ${selectedCls} ${acceptedCls}`;
         let frame_data = this._getFrameData(n);
         return (
           <div className={cls} key={n}>
            <p>{frame_data.labels.join(',')} </p>

             <BoundingBoxView
                 bboxes={frame_data.faces} path={path} ni={ni}
                 width={video.width} height={video.height}
                 onChange={this._onChange} onTrack={this._onTrack}
                 onSelect={this._onSelect} onSetTrack={this._onSetTrack}
                 onDeleteTrack={this._onDeleteTrack}/>
           </div>);
       })}
        <div>
          <Pagination prev next first last ellipsis boundaryLinks maxButtons={10}
          activePage={activePage+1} items={totalPages} onSelect={this._handlePaginationSelect}/>
        </div>
      </div>
    );
  }

  _updateRightCol() {
    if (this._rightCol !== undefined) {
      let r = boundingRect(this._rightCol);
      this._rightCol.style.maxHeight = `${window.innerHeight - r.top}px`;
    }
  }

  componentDidMount() {
    this._updateRightCol();
  }

  render() {
    let video = this.props.store;

    video.loadVideoData().then(this._onFacesLoaded.bind(this));

    if (!video.loadedMeta) {
      return <div>Loading video...</div>;
    }

    this._updateRightCol();

    return (
      <div className="video">
        <div className="row">
          <div className="col-md-4">
            {this._renderVideoSummary()}
          </div>
          <div className="col-md-8 right-col" ref={(n) => {this._rightCol = n;}}>
            {this.state.labelMode ? this._renderLabeler() : this._renderFaces()}
          </div>
        </div>
      </div>
    );
  }
};

export default (props) => <VideoView store={new models.Video(props.id)} page={props.page == null? 1 : Number(props.page)} />;
