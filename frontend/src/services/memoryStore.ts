import type { StateStore } from "oidc-client-ts";

export class MemoryStateStore implements StateStore {
  private readonly cache = new Map<string, string>();

  async set(key: string, value: string): Promise<void> {
    this.cache.set(key, value);
  }

  async get(key: string): Promise<string | null> {
    return this.cache.get(key) ?? null;
  }

  async remove(key: string): Promise<string | null> {
    const value = this.cache.get(key) ?? null;
    this.cache.delete(key);
    return value;
  }

  async getAllKeys(): Promise<string[]> {
    return Array.from(this.cache.keys());
  }
}
