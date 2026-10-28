import React from 'react';
import Header from './components/Header';
import { Card } from './components/Card.jsx';
import * as UI from './ui';

export function App() {
  return (
    <>
      <Header />
      <Card title={format('x')} />
      <UI.Button />
      <Unknown />
      <div className="x" />
    </>
  );
}

class Legacy extends React.Component {
  render() {
    return <Card />;
  }
}

function format(s) {
  return s;
}

export default Legacy;
