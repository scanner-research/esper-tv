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
      activePage: 0
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
           <u>Instructions</u>
           <ul>
             <li><b>Click/drag image</b> - make new box</li>
             <li><b>Click/drag box</b> - move box around</li>
             <li><b>space bar</b> - change gender</li>
             <li><b>d</b> - delete box</li>
             <li><b>t</b> - manage tracks</li>
             <li><b>a</b> - mark sequence as accepted</li>
             <li><b>f</b> - blow-up a frame</li>
             <li><b>c</b> - clear track/frame selection</li>
           </ul>
           <div>Current track: {this.state.curTrack || 'none'}</div>
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
    this._faces = {};
    this._allUnlabeledFaces = [];
    _.forEach(video.faces, (frames, labelset) => {
      this._faces[labelset] = {};
      _.forEach(frames, (faces, frame) => {
        this._faces[labelset][frame] = faces
          .filter((face) =>
            (face.x2 - face.x1) * (face.y2 - face.y1) > .005);
        this._allUnlabeledFaces = this._allUnlabeledFaces.concat(this._faces[labelset][frame]);
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

  _onKeyDown = (e) => {
    let chr = String.fromCharCode(e.which);
    // Clear track, first accepted frame
    if (chr == "C") {
      this.setState({
        curTrack : null,
        segStart : -1,
        lastTrackBox : -1
      });
    }
  }


  _onAccept = (ni) => {
    let curSeg = this.state.segStart;
    if (curSeg == -1) {
      this.setState({segStart: ni});
    } else {
      let video = this.props.store;
      let data = {faces: {}, video: this.props.store.id};
      let segEnd = ni;
      for (var i = this.state.segStart; i <= segEnd; ++i) {
        let idx = i * video.stride;
        let labeled_faces = this._getFacesForFrame(idx)
        let faces = labeled_faces.map((face) => face.toJSON());
        this._faces[HANDLABELED][idx] = labeled_faces
        data.faces[idx] = faces;
        this.props.store.frames[idx] = {}; // so the labeler will mark them as accepted
      }

      this.setState({segStart: -1});

      axios
        .post('/api/handlabeled', data)
        .then((_) => {
          console.log('Success');
          // do something with response?
        });
    }
  }

  _handlePaginationSelect = (selectedPage) => {
      this.setState({
          activePage: selectedPage-1
      });
  }
  _getFacesForFrame = (n) => {
     let video = this.props.store;
     let faces = []
     let labelset_id = n in video.frames ? 2 : 1;
     if (n in this._faces[labelset_id]) {
       faces = this._faces[labelset_id][n];
     } else{
       this._faces[labelset_id][n] = [];
       faces = this._faces[labelset_id][n];
     }
     return faces
  }

  _renderLabeler() {
    let video = this.props.store;

    if (!video.loadedFaces || !video.loadedFrames || !this._faces) {
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
         let selected = this.state.segStart != -1 && ni == this.state.segStart;
         let accepted = n in video.frames;
         let selectedCls = selected ? 'selected' : '';
         let acceptedCls = accepted ? 'accepted' : '';
         let cls = `bounding-box-wrapper ${selectedCls} ${acceptedCls}`;
         let faces = this._getFacesForFrame(n);
         return (
           <div className={cls} key={n}>
             <BoundingBoxView
                 bboxes={faces} path={path} ni={ni}
                 width={video.width} height={video.height}
                 onChange={this._onChange} onTrack={this._onTrack}
                 onAccept={this._onAccept} />
           </div>);
       })}
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

    video.loadFaces().then(this._onFacesLoaded.bind(this));
    video.loadFrames();

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

export default (props) => <VideoView store={new models.Video(props.id)} />;
