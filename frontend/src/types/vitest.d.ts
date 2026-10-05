/// <reference types="vitest" />
import { expect } from "vitest";

declare module "vitest" {
  interface Assertion<T = any> {
    toBeInTheDocument(): T;
    toHaveAttribute(attr: string, value?: string | RegExp): T;
    toBeVisible(): T;
    toBeDisabled(): T;
    toBeEnabled(): T;
    toHaveClass(className: string): T;
    toHaveStyle(css: string | Record<string, any>): T;
    toHaveTextContent(text: string | RegExp): T;
    toHaveValue(value: string | number | string[]): T;
    toBeChecked(): T;
    toHaveFormValues(values: Record<string, any>): T;
    toBePartiallyChecked(): T;
    toHaveErrorMessage(message: string): T;
    toBeInTheDOM(): T;
    toBeEmptyDOMElement(): T;
    toBeInvalid(): T;
    toBeRequired(): T;
    toContainElement(element: HTMLElement | null): T;
    toContainHTML(html: string): T;
  }

  interface AsymmetricMatchersContaining {
    toBeInTheDocument(): any;
    toHaveAttribute(attr: string, value?: string | RegExp): any;
    toBeVisible(): any;
    toBeDisabled(): any;
    toBeEnabled(): any;
    toHaveClass(className: string): any;
    toHaveStyle(css: string | Record<string, any>): any;
    toHaveTextContent(text: string | RegExp): any;
    toHaveValue(value: string | number | string[]): any;
    toBeChecked(): any;
    toHaveFormValues(values: Record<string, any>): any;
    toBePartiallyChecked(): any;
    toHaveErrorMessage(message: string): any;
    toBeInTheDOM(): any;
    toBeEmptyDOMElement(): any;
    toBeInvalid(): any;
    toBeRequired(): any;
    toContainElement(element: HTMLElement | null): any;
    toContainHTML(html: string): any;
  }
}
