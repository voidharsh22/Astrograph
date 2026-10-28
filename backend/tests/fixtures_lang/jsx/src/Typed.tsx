import { Component } from 'react';
import Header from './components/Header';

interface Base {
  id: number;
}

interface Props extends Base {
  label: string;
}

type Box<T> = { value: T };

export function Typed<T>(props: Props): JSX.Element {
  const box: Box<T> | null = null;
  return <Header />;
}

export class Panel extends Component<Props> {
  render() {
    return <Typed<string> label="x" id={1} />;
  }
}
