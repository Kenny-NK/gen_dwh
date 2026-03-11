import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import api, { extractListResponse } from "../services/api";

type RefetchInterval<T> = (items: T[]) => number | false;

type ListData<T> = {
  items: T[];
  total: number | null;
};

type QueryContext = {
  page: number;
  pageSize: number;
  search: string;
  signal: AbortSignal;
};

type Options<T> = {
  queryKey: readonly unknown[];
  endpoint?: string;
  pageSize?: number;
  enabled?: boolean;
  refetchInterval?: RefetchInterval<T>;
  params?: Record<string, unknown>;
  initialSearch?: string;
  resetPageDeps?: readonly unknown[];
  queryFn?: (context: QueryContext) => Promise<unknown>;
  selectData?: (data: unknown) => ListData<T>;
};

type Result<T> = UseQueryResult<ListData<T>, Error> & {
  items: T[];
  total: number | null;
  totalPages: number | null;
  hasNextPage: boolean;
  page: number;
  pageSize: number;
  search: string;
  setPage: Dispatch<SetStateAction<number>>;
  setSearch: Dispatch<SetStateAction<string>>;
};

export function useListWithPagination<T>({
  queryKey,
  endpoint,
  pageSize = 20,
  enabled = true,
  refetchInterval,
  params,
  initialSearch = "",
  resetPageDeps = [],
  queryFn,
  selectData = extractListResponse<T>,
}: Options<T>): Result<T> {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState(initialSearch);

  const queryParams = useMemo(
    () => ({
      ...(params ?? {}),
      limit: pageSize,
      offset: (page - 1) * pageSize,
    }),
    [page, pageSize, params]
  );
  const pageResetKey = JSON.stringify([search, ...resetPageDeps]);

  useEffect(() => {
    setPage(1);
  }, [pageResetKey]);

  const query = useQuery<ListData<T>, Error>({
    queryKey: [...queryKey, page, pageSize, search, params ?? null],
    queryFn: async ({ signal }) => {
      const data = queryFn
        ? await queryFn({ page, pageSize, search, signal })
        : await api.get(endpoint ?? "", { params: queryParams, signal }).then((response) => response.data);
      return selectData(data);
    },
    enabled,
    placeholderData: keepPreviousData,
    refetchInterval: refetchInterval
      ? (queryState) => {
          const data = queryState.state.data;
          return data ? refetchInterval(data.items) : false;
        }
      : false,
  });

  const total = query.data?.total ?? null;
  const totalPages = total === null ? null : Math.max(1, Math.ceil(total / pageSize));
  const hasNextPage = totalPages !== null ? page < totalPages : (query.data?.items.length ?? 0) >= pageSize;

  return {
    ...query,
    items: query.data?.items ?? [],
    total,
    totalPages,
    hasNextPage,
    page,
    pageSize,
    search,
    setPage,
    setSearch,
  };
}
