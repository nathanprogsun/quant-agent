import type { Thread, ThreadCreateParams, ThreadUpdateParams } from "./types";

const BASE_URL = "/api/v1/threads";

export async function listThreads(): Promise<Thread[]> {
    const response = await fetch(BASE_URL, {
        credentials: "include",
    });

    if (!response.ok) {
        throw new Error("Failed to fetch threads");
    }

    return response.json();
}

export async function getThread(threadId: string): Promise<Thread> {
    const response = await fetch(`${BASE_URL}/${threadId}`, {
        credentials: "include",
    });

    if (!response.ok) {
        throw new Error("Failed to fetch thread");
    }

    return response.json();
}

export async function createThread(
    params?: ThreadCreateParams
): Promise<Thread> {
    const response = await fetch(BASE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(params ?? {}),
    });

    if (!response.ok) {
        throw new Error("Failed to create thread");
    }

    return response.json();
}

export async function updateThread(
    threadId: string,
    params: ThreadUpdateParams
): Promise<Thread> {
    const response = await fetch(`${BASE_URL}/${threadId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(params),
    });

    if (!response.ok) {
        throw new Error("Failed to update thread");
    }

    return response.json();
}

export async function deleteThread(threadId: string): Promise<void> {
    const response = await fetch(`${BASE_URL}/${threadId}`, {
        method: "DELETE",
        credentials: "include",
    });

    if (!response.ok) {
        throw new Error("Failed to delete thread");
    }
}

