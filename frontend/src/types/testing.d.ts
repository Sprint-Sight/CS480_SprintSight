/// <reference types="@testing-library/jest-dom" />
import "@testing-library/jest-dom";

declare global {
  namespace Vi {
    interface Matchers<R> {
      toBeInTheDocument(): R;
      toHaveAttribute(attr: string, value?: string): R;
      toBeVisible(): R;
      toBeDisabled(): R;
      toBeEnabled(): R;
      toHaveClass(className: string): R;
      toHaveStyle(css: string | Record<string, any>): R;
      toHaveTextContent(text: string | RegExp): R;
      toHaveValue(value: string | number | string[]): R;
      toBeChecked(): R;
      toHaveFormValues(values: Record<string, any>): R;
      toBePartiallyChecked(): R;
      toHaveErrorMessage(message: string): R;
      toBeInTheDOM(): R;
      toBeEmptyDOMElement(): R;
      toBeInvalid(): R;
      toBeRequired(): R;
      toContainElement(element: HTMLElement | null): R;
      toContainHTML(html: string): R;
    }
  }
}

export {};
