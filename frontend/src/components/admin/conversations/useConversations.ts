
import { useState, useEffect } from 'react';
import { authFetch } from '@/lib/auth-client';
import { useToast } from '@/components/ui/use-toast';
import { Conversation, Message } from '@/types/database.types';

export interface ConversationDetails extends Conversation {
  messages?: Message[];
}

type SortOrder = 'asc' | 'desc';

export const useConversations = () => {
  const [conversations, setConversations] = useState<ConversationDetails[]>([]);
  const [filteredConversations, setFilteredConversations] = useState<ConversationDetails[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedConversation, setSelectedConversation] = useState<ConversationDetails | null>(null);
  const [openDialog, setOpenDialog] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const { toast } = useToast();

  const fetchConversations = async () => {
    try {
      setLoading(true);
      const API_BASE = import.meta.env.VITE_API_BASE_URL || '';
      const res = await authFetch(`${API_BASE}/api/admin/conversations?sort=${sortOrder}`);
      if (!res.ok) throw new Error(`Failed to fetch conversations: ${res.status}`);
      const data: ConversationDetails[] = await res.json();
      setConversations(data);
      setFilteredConversations(data);
    } catch (error) {
      console.error('Error fetching conversations:', error);
      toast({
        title: 'Error',
        description: 'Failed to fetch conversations',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConversations();
  }, [sortOrder]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Filter conversations based on search query
  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredConversations(conversations);
      return;
    }

    const query = searchQuery.toLowerCase().trim();
    const filtered = conversations.filter(
      (conversation) =>
        (conversation.title && conversation.title.toLowerCase().includes(query)) ||
        conversation.session_id.toLowerCase().includes(query)
    );
    setFilteredConversations(filtered);
  }, [searchQuery, conversations]);

  const toggleSortOrder = () => {
    setSortOrder(prevOrder => prevOrder === 'desc' ? 'asc' : 'desc');
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast({
      title: 'Copied',
      description: 'ID copied to clipboard',
    });
  };

  const viewConversation = async (conversation: Conversation) => {
    try {
      // Reset any previous state
      setLoadingMessages(true);
      
      // Clone the conversation object to prevent reference issues
      const conversationClone = { ...conversation };
      setSelectedConversation(conversationClone);
      setOpenDialog(true);
      
      console.log('Fetching messages for session:', conversation.session_id);
      const API_BASE = import.meta.env.VITE_API_BASE_URL || '';
      const res = await authFetch(`${API_BASE}/api/admin/conversations/${conversation.session_id}/messages`);
      if (!res.ok) throw new Error(`Failed to fetch messages: ${res.status}`);
      const messages: Message[] = await res.json();
      console.log('Fetched messages:', messages);
      
      // Use the functional update to ensure we're working with the most current state
      setSelectedConversation((prev) => {
        if (!prev) return null;
        return { ...prev, messages };
      });
    } catch (error) {
      console.error('Error fetching messages:', error);
      toast({
        title: 'Error',
        description: 'Failed to load conversation messages',
        variant: 'destructive',
      });
    } finally {
      // Always ensure loading state is reset regardless of success/failure
      setLoadingMessages(false);
    }
  };

  // Handle dialog open/close state
  const handleDialogChange = (open: boolean) => {
    setOpenDialog(open);
    if (!open) {
      // Only reset selected conversation when dialog is explicitly closed
      setSelectedConversation(null);
    }
  };

  return {
    conversations,
    filteredConversations,
    loading,
    selectedConversation,
    openDialog,
    loadingMessages,
    searchQuery,
    setSearchQuery,
    copyToClipboard,
    viewConversation,
    handleDialogChange,
    sortOrder,
    toggleSortOrder,
  };
};
