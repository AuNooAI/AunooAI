/**
 * ManageKeywordsModal - Modal for managing keyword groups and keywords
 */

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Badge } from '../ui/badge';
import { ScrollArea } from '../ui/scroll-area';
import {
  Plus,
  Trash2,
  Edit2,
  X,
  Check,
  ChevronDown,
  ChevronRight,
  Loader2,
  FolderPlus,
} from 'lucide-react';
import type { KeywordGroup, MonitoredKeyword } from '../../services/gatherApi';

interface ManageKeywordsModalProps {
  isOpen: boolean;
  onClose: () => void;
  groups: KeywordGroup[];
  keywords: MonitoredKeyword[];
  topics: string[];
  onCreateGroup: (name: string, topic: string) => Promise<KeywordGroup | null>;
  onDeleteGroup: (groupId: number) => Promise<boolean>;
  onAddKeyword: (groupId: number, keyword: string) => Promise<MonitoredKeyword | null>;
  onEditKeyword: (keywordId: number, keyword: string) => Promise<boolean>;
  onDeleteKeyword: (keywordId: number) => Promise<boolean>;
}

export function ManageKeywordsModal({
  isOpen,
  onClose,
  groups,
  keywords,
  topics,
  onCreateGroup,
  onDeleteGroup,
  onAddKeyword,
  onEditKeyword,
  onDeleteKeyword,
}: ManageKeywordsModalProps) {
  // New group form
  const [showNewGroupForm, setShowNewGroupForm] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [newGroupTopic, setNewGroupTopic] = useState('');
  const [creatingGroup, setCreatingGroup] = useState(false);

  // Expanded groups
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());

  // Editing state
  const [editingKeywordId, setEditingKeywordId] = useState<number | null>(null);
  const [editingKeywordValue, setEditingKeywordValue] = useState('');

  // New keyword state (per group)
  const [addingKeywordGroupId, setAddingKeywordGroupId] = useState<number | null>(null);
  const [newKeywordValue, setNewKeywordValue] = useState('');
  const [savingKeyword, setSavingKeyword] = useState(false);

  // Delete confirmation
  const [deletingGroupId, setDeletingGroupId] = useState<number | null>(null);

  const toggleGroup = (groupId: number) => {
    setExpandedGroups(prev => {
      const newSet = new Set(prev);
      if (newSet.has(groupId)) {
        newSet.delete(groupId);
      } else {
        newSet.add(groupId);
      }
      return newSet;
    });
  };

  const handleCreateGroup = async () => {
    if (!newGroupName.trim() || !newGroupTopic) return;

    setCreatingGroup(true);
    const result = await onCreateGroup(newGroupName.trim(), newGroupTopic);
    setCreatingGroup(false);

    if (result) {
      setNewGroupName('');
      setNewGroupTopic('');
      setShowNewGroupForm(false);
      // Auto-expand the new group
      setExpandedGroups(prev => new Set(prev).add(result.id));
    }
  };

  const handleDeleteGroup = async (groupId: number) => {
    const success = await onDeleteGroup(groupId);
    if (success) {
      setDeletingGroupId(null);
      setExpandedGroups(prev => {
        const newSet = new Set(prev);
        newSet.delete(groupId);
        return newSet;
      });
    }
  };

  const handleStartAddKeyword = (groupId: number) => {
    setAddingKeywordGroupId(groupId);
    setNewKeywordValue('');
    // Make sure group is expanded
    setExpandedGroups(prev => new Set(prev).add(groupId));
  };

  const handleAddKeyword = async () => {
    if (!addingKeywordGroupId || !newKeywordValue.trim()) return;

    setSavingKeyword(true);
    await onAddKeyword(addingKeywordGroupId, newKeywordValue.trim());
    setSavingKeyword(false);
    setNewKeywordValue('');
    setAddingKeywordGroupId(null);
  };

  const handleStartEdit = (keyword: MonitoredKeyword) => {
    setEditingKeywordId(keyword.id);
    setEditingKeywordValue(keyword.keyword);
  };

  const handleSaveEdit = async () => {
    if (editingKeywordId && editingKeywordValue.trim()) {
      await onEditKeyword(editingKeywordId, editingKeywordValue.trim());
    }
    setEditingKeywordId(null);
    setEditingKeywordValue('');
  };

  const handleCancelEdit = () => {
    setEditingKeywordId(null);
    setEditingKeywordValue('');
  };

  const getGroupKeywords = (groupId: number) => {
    return keywords.filter(k => k.group_id === groupId);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="gather-modal gather-manage-keywords-modal">
        <DialogHeader>
          <DialogTitle className="gather-modal-title">
            Manage Keywords
          </DialogTitle>
          <DialogDescription>
            Create and manage keyword groups for article collection
          </DialogDescription>
        </DialogHeader>

        <div className="gather-modal-content">
          {/* New Group Button/Form */}
          {showNewGroupForm ? (
            <div className="gather-new-group-form">
              <div className="gather-form-row">
                <div className="gather-form-group">
                  <Label htmlFor="group-name">Group Name</Label>
                  <Input
                    id="group-name"
                    placeholder="e.g., AI Industry Leaders"
                    value={newGroupName}
                    onChange={e => setNewGroupName(e.target.value)}
                    disabled={creatingGroup}
                  />
                </div>
                <div className="gather-form-group">
                  <Label htmlFor="group-topic">Topic</Label>
                  <Select value={newGroupTopic} onValueChange={setNewGroupTopic} disabled={creatingGroup}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select topic..." />
                    </SelectTrigger>
                    <SelectContent>
                      {topics.map(topic => (
                        <SelectItem key={topic} value={topic}>
                          {topic}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="gather-form-actions">
                <Button
                  onClick={handleCreateGroup}
                  disabled={!newGroupName.trim() || !newGroupTopic || creatingGroup}
                >
                  {creatingGroup ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    <>
                      <Plus className="h-4 w-4" />
                      Create Group
                    </>
                  )}
                </Button>
                <Button variant="outline" onClick={() => setShowNewGroupForm(false)} disabled={creatingGroup}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <Button
              onClick={() => setShowNewGroupForm(true)}
              className="gather-new-group-button"
            >
              <FolderPlus className="h-4 w-4" />
              New Keyword Group
            </Button>
          )}

          {/* Groups List */}
          <ScrollArea className="gather-groups-list">
            {groups.length === 0 ? (
              <div className="gather-empty-groups">
                <p>No keyword groups yet. Create one to get started.</p>
              </div>
            ) : (
              groups.map(group => {
                const groupKeywords = getGroupKeywords(group.id);
                const isExpanded = expandedGroups.has(group.id);
                const isDeleting = deletingGroupId === group.id;

                return (
                  <div key={group.id} className="gather-group-item">
                    {/* Group Header */}
                    <div className="gather-group-header" onClick={() => toggleGroup(group.id)}>
                      <div className="gather-group-toggle">
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </div>
                      <div className="gather-group-info">
                        <span className="gather-group-name">{group.name}</span>
                        <Badge variant="secondary" className="gather-group-topic">
                          {group.topic}
                        </Badge>
                        <span className="gather-group-count">
                          {groupKeywords.length} keyword{groupKeywords.length !== 1 ? 's' : ''}
                        </span>
                      </div>
                      <div className="gather-group-actions" onClick={e => e.stopPropagation()}>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleStartAddKeyword(group.id)}
                        >
                          <Plus className="h-4 w-4" />
                        </Button>
                        {isDeleting ? (
                          <div className="gather-delete-inline">
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() => handleDeleteGroup(group.id)}
                            >
                              Confirm
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setDeletingGroupId(null)}
                            >
                              Cancel
                            </Button>
                          </div>
                        ) : (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setDeletingGroupId(group.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Expanded Content */}
                    {isExpanded && (
                      <div className="gather-group-keywords">
                        {groupKeywords.map(kw => (
                          <div key={kw.id} className="gather-keyword-row">
                            {editingKeywordId === kw.id ? (
                              <div className="gather-keyword-edit-inline">
                                <Input
                                  value={editingKeywordValue}
                                  onChange={e => setEditingKeywordValue(e.target.value)}
                                  onKeyDown={e => {
                                    if (e.key === 'Enter') handleSaveEdit();
                                    if (e.key === 'Escape') handleCancelEdit();
                                  }}
                                  autoFocus
                                />
                                <Button size="sm" variant="ghost" onClick={handleSaveEdit}>
                                  <Check className="h-4 w-4" />
                                </Button>
                                <Button size="sm" variant="ghost" onClick={handleCancelEdit}>
                                  <X className="h-4 w-4" />
                                </Button>
                              </div>
                            ) : (
                              <>
                                <span className="gather-keyword-text">{kw.keyword}</span>
                                <div className="gather-keyword-actions">
                                  <Button size="sm" variant="ghost" onClick={() => handleStartEdit(kw)}>
                                    <Edit2 className="h-3 w-3" />
                                  </Button>
                                  <Button size="sm" variant="ghost" onClick={() => onDeleteKeyword(kw.id)}>
                                    <X className="h-3 w-3" />
                                  </Button>
                                </div>
                              </>
                            )}
                          </div>
                        ))}

                        {/* Add keyword input (inline) */}
                        {addingKeywordGroupId === group.id && (
                          <div className="gather-keyword-add-inline">
                            <Input
                              placeholder="Enter keyword..."
                              value={newKeywordValue}
                              onChange={e => setNewKeywordValue(e.target.value)}
                              onKeyDown={e => {
                                if (e.key === 'Enter') handleAddKeyword();
                                if (e.key === 'Escape') setAddingKeywordGroupId(null);
                              }}
                              disabled={savingKeyword}
                              autoFocus
                            />
                            <Button
                              size="sm"
                              onClick={handleAddKeyword}
                              disabled={!newKeywordValue.trim() || savingKeyword}
                            >
                              {savingKeyword ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Plus className="h-4 w-4" />
                              )}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setAddingKeywordGroupId(null)}
                            >
                              <X className="h-4 w-4" />
                            </Button>
                          </div>
                        )}

                        {groupKeywords.length === 0 && addingKeywordGroupId !== group.id && (
                          <div className="gather-keywords-empty">
                            <p>No keywords in this group</p>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleStartAddKeyword(group.id)}
                            >
                              <Plus className="h-4 w-4" />
                              Add First Keyword
                            </Button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  );
}
