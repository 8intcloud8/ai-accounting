import type { Plugin } from "vite";
export function viteSingleFile(): Plugin;
export function replaceScript(html: string, filename: string, code: string): string;
export function replaceCss(html: string, filename: string, code: string): string;
