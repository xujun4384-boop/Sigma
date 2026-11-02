import {createContext, useContext} from 'react';
import type {E} from '../types';

const EngineContext = createContext<E | null>(null);

export const EngineProvider = EngineContext.Provider;

/** 画面代码用这个拿环境对象（等价于 canvas 版的 draw(e) 里的 e） */
export const useE = (): E => {
  const e = useContext(EngineContext);
  if (!e) throw new Error('useE() 必须在 <SceneHost> 之内使用');
  return e;
};

export const useOptionalE = () => useContext(EngineContext);
