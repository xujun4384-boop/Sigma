import React from 'react';

type Err = {scene: string; message: string; frame: number};

declare global {
  interface Window {
    __mvErrors?: Err[];
    __mvFrame?: number;
  }
}

/** 单个镜头崩溃只降级这个镜头，不整片红屏；错误写进 window.__mvErrors 供闸门读取 */
export class SceneBoundary extends React.Component<
  {scene: string; children: React.ReactNode; fallback?: React.ReactNode; strict?: boolean},
  {failed: boolean}
> {
  state = {failed: false};

  static getDerivedStateFromError() {
    return {failed: true};
  }

  componentDidCatch(error: Error) {
    const err: Err = {
      scene: this.props.scene,
      message: `${error.name}: ${error.message}`,
      frame: typeof window !== 'undefined' ? window.__mvFrame ?? -1 : -1,
    };
    if (typeof window !== 'undefined') {
      window.__mvErrors = window.__mvErrors || [];
      const last = window.__mvErrors[window.__mvErrors.length - 1];
      if (!last || last.scene !== err.scene || last.message !== err.message) window.__mvErrors.push(err);
    }
  }

  render() {
    if (this.props.strict) return this.props.children;
    if (this.state.failed) return this.props.fallback ?? null;
    return this.props.children;
  }
}
