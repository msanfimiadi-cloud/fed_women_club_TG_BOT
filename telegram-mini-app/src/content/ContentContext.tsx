import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  getContentBlocks,
  getHomeBlocks,
  type HomeBlock,
} from "./clientContentApi";

interface ContentContextValue {
  blocks: Record<string, string>;
  homeBlocks: HomeBlock[];
  isLoading: boolean;
  loadError: string;
  getText: (key: string, fallback: string) => string;
}

const ContentContext = createContext<ContentContextValue | null>(null);

function mapBlocks(
  blocks: Awaited<ReturnType<typeof getContentBlocks>>,
): Record<string, string> {
  return blocks.reduce<Record<string, string>>((acc, block) => {
    acc[block.key] = block.value;
    return acc;
  }, {});
}

function sortHomeBlocks(items: HomeBlock[]): HomeBlock[] {
  return [...items].sort((left, right) => left.sort_order - right.sort_order);
}

export function ContentProvider({ children }: PropsWithChildren) {
  const [blocks, setBlocks] = useState<Record<string, string>>({});
  const [homeBlocks, setHomeBlocks] = useState<HomeBlock[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setLoadError("");

    Promise.allSettled([getContentBlocks(), getHomeBlocks()])
      .then(([textResult, homeResult]) => {
        if (!isMounted) {
          return;
        }

        if (textResult.status === "fulfilled") {
          setBlocks(mapBlocks(textResult.value));
        }

        if (homeResult.status === "fulfilled") {
          setHomeBlocks(sortHomeBlocks(homeResult.value));
        }

        if (textResult.status === "rejected" || homeResult.status === "rejected") {
          const failedSources = [
            textResult.status === "rejected"
              ? `тексты: ${textResult.reason instanceof Error ? textResult.reason.message : "неизвестная ошибка"}`
              : null,
            homeResult.status === "rejected"
              ? `блоки главной: ${homeResult.reason instanceof Error ? homeResult.reason.message : "неизвестная ошибка"}`
              : null,
          ].filter(Boolean);
          setLoadError(
            `Не удалось загрузить контент (${failedSources.join("; ")}). Используются данные по умолчанию.`,
          );
          return;
        }

        setLoadError("");
      })
      .finally(() => {
        if (isMounted) {
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const getText = useCallback(
    (key: string, fallback: string) => {
      const value = blocks[key];
      return value === undefined || value === "" ? fallback : value;
    },
    [blocks],
  );

  const value = useMemo<ContentContextValue>(
    () => ({ blocks, homeBlocks, isLoading, loadError, getText }),
    [blocks, getText, homeBlocks, isLoading, loadError],
  );

  return <ContentContext.Provider value={value}>{children}</ContentContext.Provider>;
}

export function useContent() {
  const context = useContext(ContentContext);

  if (!context) {
    throw new Error("useContent must be used inside ContentProvider");
  }

  return context;
}

export function useContentText(key: string, fallback: string): string {
  return useContent().getText(key, fallback);
}
