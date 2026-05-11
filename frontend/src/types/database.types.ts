export interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  is_admin: boolean;
}

export interface AuthSession {
  access_token: string;
  user: AuthUser;
}

export interface Conversation {
  session_id: string;
  title: string | null;
  created_at: string;
  last_message_at: string;
}

export interface Message {
  id: number | string;
  session_id: string;
  message: {
    type: "human" | "ai";
    content: string;
    files?: FileAttachment[];
    trace_id?: string;
  };
  created_at: string;
}

export interface FileAttachment {
  fileName: string;
  content: string;
  mimeType: string;
}

export interface Profile {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  is_admin: boolean;
}
