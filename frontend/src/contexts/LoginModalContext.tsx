"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

interface LoginModalContextValue {
  isOpen: boolean;
  openLoginModal: () => void;
  closeLoginModal: () => void;
}

const LoginModalContext = createContext<LoginModalContextValue | null>(null);

interface LoginModalProviderProps {
  children: ReactNode;
  defaultOpen?: boolean;
}

export function LoginModalProvider({
  children,
  defaultOpen = false,
}: LoginModalProviderProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  const openLoginModal = useCallback(() => setIsOpen(true), []);
  const closeLoginModal = useCallback(() => setIsOpen(false), []);

  const value = useMemo(
    () => ({ isOpen, openLoginModal, closeLoginModal }),
    [isOpen, openLoginModal, closeLoginModal],
  );

  return (
    <LoginModalContext.Provider value={value}>
      {children}
    </LoginModalContext.Provider>
  );
}

export function useLoginModal(): LoginModalContextValue {
  const context = useContext(LoginModalContext);
  if (!context) {
    throw new Error("useLoginModal must be used within LoginModalProvider");
  }
  return context;
}
