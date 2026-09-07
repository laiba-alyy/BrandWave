'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface DeleteAccountModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => Promise<void>
  loading?: boolean
  /** Backend se aayi asli failure wajah — khali string matlab koi error nahi. */
  error?: string
}

export default function DeleteAccountModal({
  isOpen,
  onClose,
  onConfirm,
  loading = false,
  error = '',
}: DeleteAccountModalProps) {
  const [typed, setTyped] = useState('')
  const confirmationText = 'DELETE MY ACCOUNT'

  const isConfirmed = typed === confirmationText

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm"
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-3xl border border-red-200 bg-white p-8 shadow-2xl shadow-red-950/20"
          >
            {/* Icon */}
            <div className="text-center mb-6">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-red-50 text-4xl ring-1 ring-red-100">⚠️</div>
              <h2 className="mb-2 text-2xl font-black text-red-600">Delete Account?</h2>
              <p className="text-sm leading-relaxed text-gray-500">
                This action cannot be undone. All your data will be permanently deleted.
              </p>
            </div>

            {/* Warning Box */}
            <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-4">
              <p className="text-sm font-bold leading-relaxed text-red-700">
                ❌ Your business data, settings, and profile will be deleted forever.
              </p>
            </div>

            {/* Confirmation Input */}
            <div className="mb-6">
              <label className="mb-2 block text-sm font-bold text-gray-700">
                Type <span className="text-red-600">{confirmationText}</span> to confirm:
              </label>
              <input
                type="text"
                value={typed}
                onChange={(e) => setTyped(e.target.value.toUpperCase())}
                placeholder="Type here..."
                className="w-full rounded-xl border border-gray-200 bg-white px-4 py-3 font-mono text-sm text-gray-900 shadow-sm transition-all placeholder:text-gray-400 focus:border-red-500 focus:outline-none focus:ring-4 focus:ring-red-100"
              />
              <p className="mt-2 text-xs font-semibold text-gray-400">
                {typed.length}/{confirmationText.length}
              </p>
            </div>

            {/* Failure — modal khula rehta hai taake user retry kar sake */}
            {error && (
              <div className="mb-6 rounded-2xl border border-red-300 bg-red-100 p-4" role="alert">
                <p className="text-sm font-bold text-red-800">Deletion failed</p>
                <p className="mt-1 text-xs leading-relaxed text-red-700">{error}</p>
              </div>
            )}

            {/* Buttons */}
            <div className="flex gap-3">
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={onClose}
                disabled={loading}
                className="flex-1 rounded-xl bg-gray-100 px-4 py-3 font-bold text-gray-700 transition-all hover:bg-gray-200 hover:text-gray-950 disabled:opacity-50"
              >
                Cancel
              </motion.button>
              <motion.button
                whileHover={{ scale: isConfirmed && !loading ? 1.02 : 1 }}
                whileTap={{ scale: isConfirmed && !loading ? 0.98 : 1 }}
                onClick={onConfirm}
                disabled={!isConfirmed || loading}
                className="flex-1 rounded-xl bg-red-600 px-4 py-3 font-bold text-white shadow-lg shadow-red-600/20 transition-all hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
              >
                {loading ? '🗑️ Deleting...' : '🗑️ Delete Account'}
              </motion.button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}