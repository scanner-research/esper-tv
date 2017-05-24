import React from 'react';
import {Video} from 'models/video.jsx';
import VideoSummary from 'views/video_summary.jsx';
import {observer} from 'mobx-react';
import mobx from 'mobx';
import _ from 'lodash';
import {Button, Collapse} from 'react-bootstrap';

@observer
class VideoView extends React.Component {
  constructor(...args) {
    super(...args);
    this.state = {showAllFaces: false};
  }

  render() {
    let video = this.props.store;

    if (!video.loadedMeta) {
      return <div>Loading video...</div>;
    }

    video.loadFaces();

    let table = [
      ['ID', video.id],
      ['Path', video.path],
      ['# frames', video.num_frames],
      ['FPS', video.fps],
      ['Resolution', `${video.width}x${video.height}`]];

    return (
      <div className="video">
        <div className="row">
          <div className="pull-left">
            <VideoSummary store={video} show_meta={false} />
          </div>
          <div className="pull-right">
            <h2>Metadata</h2>
            <table className="table">
              <tbody>
                {table.map((pair, i) =>
                  <tr key={i}><td>{pair[0]}</td><td>{pair[1]}</td></tr>
                 )}
              </tbody>
            </table>
          </div>
        </div>
        <div className="cluster">
          <h3>All faces
            &nbsp; <Button onClick={() => this.setState({showAllFaces: !this.state.showAllFaces})}>+</Button>
          </h3>
          <Collapse in={this.state.showAllFaces}>
            <div>
              {video.loadedFaces
               ? _.map(video.faces, (faces, i) =>
                 <div className="frame" key={i}>
                   {faces.map((face, j) =>
                     <img key={j} src={`/static/thumbnails/${face.video}_${face.id}.jpg`} />)}
                 </div>
               )
               : <div />}
            </div>
          </Collapse>
        </div>
        <div className="clusters">
          {video.loadedFaces
           ? _.map(video.ids, (faces, i) =>
             <div className="cluster" key={i}>
               <h3>Cluster {i}</h3>
               {faces.map((entry, j) => {
                  let [frame, face_index] = entry;
                  let frame_faces = video.faces[frame];
                  let face = frame_faces[face_index];
                  return (
                    <img key={j} src={`/static/thumbnails/${face.video}_${face.id}.jpg`} />
                  );
                })}
             </div>
           )
           : (<div>Loading faces...</div>)
          }
        </div>
      </div>
    );
  }
};

export default (props) => <VideoView store={new Video(props.id)} />;
