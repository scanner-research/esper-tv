import React from 'react';
import {observer} from 'mobx-react';
import mobx from 'mobx';
import _ from 'lodash';
import {Button, Collapse} from 'react-bootstrap';
import leftPad from 'left-pad';

import {Video} from 'models/video.jsx';
import VideoSummary from 'views/video_summary.jsx';
import {Box, BoundingBoxView} from 'views/bbox.jsx';

@observer
class VideoView extends React.Component {
  constructor(...args) {
    super(...args);
    this.state = {
      showAllFaces: false,
      frame: 0,
      labelMode: true
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
      </div>
    );
  }

  _renderFace(face, j) {
    return <img key={j} src={`/static/thumbnails/${face.video}_${face.id}.jpg`}
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

  _renderLabeler() {
    let video = this.props.store;
    let all_boxes = [];
    return (
      <div className='video-labeler'>
        {_.range(0, video.num_frames, 24).map((n) => {
           let path = `/static/thumbnails/${video.id}_frame_${leftPad(n+1, 6, '0')}.jpg`;
           let boxes = [];
           if (n in video.faces) {
             let faces = video.faces[n];
             boxes = faces.map((face) =>
               new Box(face.bbox.x1, face.bbox.y1,
                       face.bbox.x2, face.bbox.y2,
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

           return <BoundingBoxView
                      key={n} bboxes={boxes} path={path}
                      width={video.width} height={video.height}
                      onChange={onChange} />;
         })}
      </div>
    );
  }

  render() {
    let video = this.props.store;

    video.loadFaces();

    if (!video.loadedMeta) {
      return <div>Loading video...</div>;
    }

    return (
      <div className="video">
        <div className="row">
          <div className="col-md-4">
            {this._renderVideoSummary()}
          </div>
          <div className="col-md-8">
            {this.state.labelMode ? this._renderLabeler() : this._renderFaces()}
          </div>
        </div>
      </div>
    );
  }
};

export default (props) => <VideoView store={new Video(props.id)} />;
