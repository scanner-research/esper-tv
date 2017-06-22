import React from 'react';
import {observer} from 'mobx-react';
import mobx from 'mobx';
import _ from 'lodash';
import {Button, Collapse, Pagination} from 'react-bootstrap';
import leftPad from 'left-pad';

import * as models from 'models/mod.jsx';
import VideoSummary from './video_summary.jsx';
import {Box, BoundingBoxView, boundingRect} from './bbox.jsx';

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

  _handlePaginationSelect = (selectedPage) => {
      this.setState({
          activePage: selectedPage-1
      });
  }
      

  _renderLabeler() {
    let video = this.props.store;
    const stride = Math.ceil(video.fps)/3;
    let all_boxes = [];
    // TODO: doing something generic here (passing a list of items)
    // is challenging becaues of the way bounding boxes are drawn
    // I will revisit this when this is set in stone
    const framesPerPage = 200;
    const totalPages = video.num_frames/(stride*framesPerPage);
    const activePage = this.state.activePage;
    const firstFrame = activePage*framesPerPage*stride;
    const lastFrame = Math.min(firstFrame+(framesPerPage*stride), video.num_frames);


    return (
      <div className='video-labeler'>
      <div>
      <Pagination prev next first last ellipsis boundaryLinks maxButtons={10} 
      activePage={activePage+1} items={totalPages} onSelect={this._handlePaginationSelect}/>
      </div>
        {_.range(firstFrame, lastFrame, stride).map((n, ni) => {
           let path = `/static/thumbnails/${video.id}_frame_${leftPad(n+1, 6, '0')}.jpg`;
           let boxes = [];
           if (n in video.faces) {
             let faces = video.faces[n];
             boxes = faces
               .filter((face) =>
                 (face.bbox.x2 - face.bbox.x1) * (face.bbox.y2 - face.bbox.y1) > 2000)
               .map((face) =>
                 new Box(face.bbox.x1/video.width, face.bbox.y1/video.height,
                         face.bbox.x2/video.width, face.bbox.y2/video.height,
                         `gender-${face.gender}`,
                         face.track)
               );
             all_boxes = all_boxes.concat(boxes);
           }

           let onChange = (box) => {
             if (box.track == null) { return; }
             all_boxes.forEach((other_box) => {
               if (box.track == other_box.track) {
                 other_box.cls = box.cls;
               }
             });
           };

           let onTrack = (box) => {
             let i = all_boxes.indexOf(box);
             if (i == this.state.lastTrackBox) {
               console.log('Ending track');
               this.setState({curTrack: null, lastTrackBox: -1});
             } else if (this.state.curTrack == null) {
               console.log('Creating track');
               let track = box.track;
               if (track == null) {
                 box.track = 100;
                 track = box.track;
               }
               this.setState({curTrack: track, lastTrackBox: i});
             } else {
               console.log('Adding to track')
               box.track = this.state.curTrack;
               this.setState({lastTrackBox: i});
             }
           };

           let onAccept = () => {
             let curSeg = this.state.segStart;
             if (curSeg == -1) {
               this.setState({segStart: ni});
             } else if (curSeg == ni) {
               this.setState({segStart: -1});
             } else {
               console.log('segment');
             }
           };

           return <BoundingBoxView
                      key={n} bboxes={boxes} path={path}
                      selected={this.state.segStart != -1 && ni == this.state.segStart}
                      width={video.width} height={video.height}
                      onChange={onChange} onTrack={onTrack} onAccept={onAccept} />;
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

    video.loadFaces();

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
