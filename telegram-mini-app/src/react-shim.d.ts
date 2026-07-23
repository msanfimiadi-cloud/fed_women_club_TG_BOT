declare module 'react' {
  export type PropsWithChildren<P = unknown> = P & { children?: ReactNode };
  export type ReactNode = unknown;
  export type ElementType = keyof JSX.IntrinsicElements | ((props: any) => unknown);
  export interface KeyboardEvent<T = Element> { key: string; preventDefault(): void; stopPropagation(): void; currentTarget: T; }
  export type Dispatch<A> = (value: A) => void;
  export type SetStateAction<S> = S | ((previousState: S) => S);
  export interface RefObject<T> {
    current: T;
  }
  export interface FormEvent<T = Element> {
    preventDefault(): void;
    currentTarget: T;
  }

  export interface ErrorInfo {
    componentStack?: string | null;
  }

  export class Component<P = unknown, S = unknown> {
    constructor(props: P);
    props: Readonly<P>;
    state: Readonly<S>;
    setState(state: Partial<S> | S): void;
    render(): ReactNode;
  }

  export interface Context<T> { Provider: (props: { value: T; children?: ReactNode }) => unknown }
  export function createContext<T>(defaultValue: T): Context<T>;
  export function useCallback<T extends (...args: any[]) => unknown>(callback: T, deps: unknown[]): T;
  export function useEffect(effect: () => void | (() => void), deps?: unknown[]): void;
  export function useContext<T>(context: Context<T>): T;
  export function useId(): string;
  export function useMemo<T>(factory: () => T, deps: unknown[]): T;
  export function useRef<T>(initialValue: T): RefObject<T>;
  export function useState<S>(initialState: S | (() => S)): [S, Dispatch<SetStateAction<S>>];

  const React: {
    createElement(type: unknown, props?: unknown, ...children: unknown[]): unknown;
    StrictMode: (props: { children?: ReactNode }) => unknown;
  };

  export default React;
}

declare module 'react-dom' {
  export function createPortal(children: unknown, container: Element | DocumentFragment): unknown;
}

declare module 'react-dom/client' {
  export function createRoot(container: HTMLElement): {
    render(children: unknown): void;
  };
}

declare module 'react/jsx-runtime' {
  export const Fragment: unknown;
  export function jsx(type: unknown, props: unknown, key?: unknown): unknown;
  export function jsxs(type: unknown, props: unknown, key?: unknown): unknown;
}

declare namespace JSX {
  interface IntrinsicElements {
    [elementName: string]: unknown;
  }
}

declare module '*.css';
