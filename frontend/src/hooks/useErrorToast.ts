import { useCallback } from "react";

import { useToast } from "../components/common/Toast";
import { extractApiErrorMessage } from "../services/api";

export function useErrorToast() {
  const { addToast } = useToast();

  const showErrorToast = useCallback(
    (error: unknown, fallback: string) => {
      addToast("error", extractApiErrorMessage(error, fallback));
    },
    [addToast]
  );

  return {
    showErrorToast,
    getErrorMessage: useCallback(
      (error: unknown, fallback: string) => extractApiErrorMessage(error, fallback),
      []
    ),
  };
}
