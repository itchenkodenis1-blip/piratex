export interface Translations {
  // App
  app_loading: string;
  app_tagline: string;

  // Auth
  auth_error_generic: string;
  auth_error_connection: string;

  // Navigation
  nav_analysis: string;
  nav_library: string;
  nav_settings: string;
  nav_logout: string;

  // Home page
  home_title: string;
  home_subtitle: string;
  home_new_analysis: string;
  home_try_again: string;
  home_error_fetch: string;
  home_error_processing: string;
  home_error_submit: string;

  // URL Input
  input_placeholder: string;
  input_processing: string;
  input_submit: string;

  // Status labels
  status_pending: string;
  status_downloading: string;
  status_extracting_audio: string;
  status_transcribing: string;
  status_detecting_scenes: string;
  status_extracting_frames: string;
  status_analyzing_frames: string;
  status_generating_summary: string;
  status_completed: string;
  status_failed: string;

  // Pipeline steps
  pipeline_download: string;
  pipeline_audio: string;
  pipeline_transcribe: string;
  pipeline_scenes: string;
  pipeline_frames: string;
  pipeline_analyze: string;
  pipeline_summary: string;
  script_writing_title: string;
  script_writing_script: string;
  script_writing_description: string;
  script_writing_editor: string;
  script_writing_strategy: string;

  // Scene types
  scene_talking_head: string;
  scene_screencast: string;
  scene_animation: string;
  scene_text_card: string;
  scene_split_screen: string;
  scene_b_roll: string;

  // Frame analysis
  frame_speech: string;
  frame_text_on_screen: string;
  frame_visual: string;
  frame_analyzing: string;

  // Waiting state
  waiting_connecting: string;
  waiting_subtitle: string;

  // Results sections
  results_frame_breakdown: string;
  results_transcript: string;
  results_final: string;
  results_views: string;
  results_likes: string;
  results_comments: string;

  // Transcript panel
  transcript_title: string;
  transcript_copied: string;
  transcript_copy: string;

  // Adaptation summary
  summary_copied: string;
  summary_copy: string;
  summary_script: string;
  summary_description: string;
  summary_editor_instructions: string;
  summary_second_language: string;
  summary_translation_generate: string;
  summary_translating: string;
  summary_translation_stale: string;
  summary_translation_refresh: string;
  summary_translation_error: string;
  settings_dual_language: string;
  settings_dual_language_hint: string;
  settings_second_language: string;
  summary_hook_variants: string;
  summary_hook_variant_label: string;
  hook_in_use: string;
  hook_use: string;
  hook_badge_best: string;
  hook_badge_strong: string;
  hook_badge_alternative: string;
  hook_timing_sec: string;
  hook_timing_warning: string;
  hook_refine: string;
  hook_refine_strengthen: string;
  hook_refine_shorter: string;
  hook_refine_audience: string;
  summary_hashtags: string;
  strategy_section_title: string;
  strategy_virality: string;
  strategy_show_more: string;
  strategy_show_less: string;

  // Library page
  library_title: string;
  library_count: string;
  library_search_placeholder: string;
  library_sort_recent: string;
  library_sort_popular: string;
  library_loading: string;
  library_empty_search: string;
  library_empty: string;
  library_prev: string;
  library_next: string;
  library_tags_filter: string;
  library_tags_search: string;

  // Library reel detail
  library_reel_loading: string;
  library_reel_not_found: string;
  library_reel_error: string;
  library_reel_back: string;
  library_reel_back_arrow: string;
  library_reel_bookmarked: string;
  library_reel_save: string;
  library_reel_adapt: string;

  // Reel card
  reel_no_title: string;
  reel_has_script: string;

  // Script generation
  library_reel_my_script: string;
  library_reel_write_script: string;
  library_reel_rewrite: string;
  library_reel_no_script_yet: string;
  library_my_scripts: string;
  script_generating: string;
  script_rewriting: string;
  script_generation_error: string;
  script_step_analyzing: string;
  script_step_writing: string;
  script_step_polishing: string;
  script_rewrite_error: string;
  library_reel_rewrite_confirm: string;
  edit_script: string;
  save_script: string;
  save_script_saving: string;
  cancel_edit: string;

  // Teleprompter
  teleprompter_open: string;
  teleprompter_restart: string;
  teleprompter_font_size: string;
  teleprompter_theme: string;
  teleprompter_voice: string;
  teleprompter_voice_denied: string;

  // Settings page
  settings_title: string;
  settings_back: string;
  settings_api_keys: string;
  settings_openai_key: string;
  settings_key_set: string;
  settings_key_not_set: string;
  settings_key_placeholder: string;
  settings_save: string;
  settings_saved: string;
  settings_save_error: string;
  settings_openai_hint: string;
  settings_anthropic_key: string;
  settings_anthropic_hint: string;
  settings_language: string;
  settings_language_hint: string;
  settings_prompts: string;
  settings_content_prompt: string;
  settings_content_prompt_hint: string;
  settings_strategy_prompt: string;
  settings_strategy_prompt_hint: string;
  settings_prompt_reset: string;
  settings_prompt_reset_confirm: string;
  settings_prompt_saved: string;
  settings_prompt_using_default: string;
  settings_prompt_custom: string;

  // Profile settings
  settings_profile: string;
  settings_profile_hint: string;
  settings_about_me: string;
  settings_about_me_hint: string;
  settings_tone: string;
  settings_tone_custom_placeholder: string;
  settings_script_cta: string;
  settings_script_cta_hint: string;
  settings_description_cta: string;
  settings_description_cta_hint: string;
  settings_forbidden_words: string;
  settings_forbidden_words_hint: string;
  settings_video_format: string;
  settings_video_format_custom_placeholder: string;
  settings_advanced_mode: string;
  settings_advanced_mode_hint: string;
  settings_advanced_warning: string;
  settings_profile_saved: string;
  settings_profile_reset: string;
  settings_profile_reset_confirm: string;
  settings_custom_format: string;

  // My Videos page
  nav_my_videos: string;
  my_videos_title: string;
  my_videos_count: string;
  my_videos_empty: string;
  my_videos_filter_all: string;
  my_videos_filter_processing: string;
  my_videos_filter_completed: string;
  my_videos_filter_failed: string;
  filter_liked: string;
  my_videos_status_processing: string;
  my_videos_status_ready: string;
  my_videos_status_failed: string;
  my_videos_status_filmed: string;
  my_videos_filmed: string;
  my_videos_not_filmed: string;
  my_videos_view_result: string;
  my_videos_hide: string;
  my_videos_loading: string;

  // Anonymous / usage limits
  nav_login: string;
  usage_anonymous_limit: string;
  usage_telegram_required: string;
  usage_monthly_limit: string;
  usage_telegram_unsubscribed: string;
  usage_display: string;
  usage_display_month: string;
  auth_required_page: string;

  // Share
  share_copy_link: string;
  share_link_copied: string;
  shared_page_not_found: string;
  shared_page_loading: string;
  shared_page_cta: string;
  shared_page_try_piratex: string;
  shared_page_original_reel: string;
  shared_page_keyframes: string;
  shared_page_open_reference: string;

  // AuthGateModal
  modal_close: string;
  modal_step_telegram_login: string;
  modal_step_telegram: string;
  modal_telegram_connect: string;
  modal_telegram_scan_qr: string;
  modal_telegram_open_bot: string;
  modal_telegram_code_expired: string;
  modal_telegram_retry: string;
  modal_telegram_subscribe: string;
  modal_telegram_subscribe_hint: string;
  modal_telegram_verify: string;
  modal_telegram_verifying: string;
  modal_telegram_not_subscribed: string;
  modal_telegram_error: string;
  modal_telegram_cooldown: string;
  modal_step_done: string;
  modal_done_message: string;
  modal_done_start: string;
  auth_required_login_btn: string;

  // Pricing
  nav_pricing: string;

  // Trends page
  nav_trends: string;
  trends_title: string;
  trends_subtitle: string;
  trends_loading: string;
  trends_empty: string;
  trends_error: string;
  trends_all_niches: string;
  trends_search_niches: string;
  trends_no_niches_found: string;
  trends_all_platforms: string;
  trends_sort_hot_score: string;
    trends_sort_x_factor: string;
  trends_sort_views: string;
  trends_sort_recent: string;
  trends_parse: string;
  trends_days_ago: string;
  trends_hours_ago: string;
  trends_tab_all: string;
  trends_tab_my_authors: string;
  trends_follow: string;
  trends_following: string;
  trends_new_viral: string;
  trends_caught_today: string;
  trends_add_author: string;
  trends_add_author_placeholder: string;
  trends_add_author_checking: string;
  trends_author_not_found: string;
  trends_author_limit_reached: string;
  trends_author_added: string;
  trends_open: string;

  // For You recommendations
  for_you_title: string;
  for_you_subtitle: string;
  for_you_login_cta: string;
  for_you_no_niche: string;
  trends_tab_for_you: string;
  trends_search_placeholder: string;
  trends_search_upgrade: string;
  trends_search_short: string;
  trends_period_all: string;
  trends_period_today: string;
  trends_period_week: string;
  trends_period_month: string;
  trends_period_year: string;
  for_you_personalize_cta: string;
  for_you_personalize_title: string;
  for_you_personalize_desc: string;
  for_you_analyze_btn: string;
  analyzing: string;
  for_you_analyzed_success: string;
  settings_ig_hint: string;
  settings_ig_analyze_btn: string;
  settings_ig_success: string;
  for_you_hint: string;
  for_you_hint_link: string;
  for_you_onboarding_eyebrow: string;
  for_you_onboarding_title: string;
  for_you_onboarding_subtitle: string;
  for_you_onboarding_ig_title: string;
  for_you_onboarding_ig_desc: string;
  for_you_onboarding_ig_time: string;
  for_you_onboarding_manual_title: string;
  for_you_onboarding_manual_desc: string;
  for_you_onboarding_manual_time: string;
  for_you_onboarding_dismiss: string;
  for_you_onboarding_global_label: string;
  trends_auth_required_filter: string;
  trends_upgrade_pages: string;
  trends_my_authors_empty: string;
  trends_my_authors_empty_cta: string;

  // Niche names
  niche_ai: string;
  "niche_vibe-coding": string;
  "niche_software-dev": string;
  niche_saas: string;
  "niche_no-code": string;
  niche_cybersecurity: string;
  niche_tech: string;
  niche_science: string;
  "niche_data-science": string;
  niche_business: string;
  niche_startups: string;
  niche_ecommerce: string;
  niche_finance: string;
  niche_investing: string;
  niche_crypto: string;
  niche_freelance: string;
  niche_legal: string;
  "niche_real-estate": string;
  "niche_personal-brand": string;
  niche_marketing: string;
  niche_copywriting: string;
  niche_seo: string;
  niche_smm: string;
  niche_design: string;
  niche_photography: string;
  "niche_video-production": string;
  niche_music: string;
  niche_art: string;
  niche_writing: string;
  niche_dance: string;
  niche_crafts: string;
  niche_education: string;
  niche_career: string;
  niche_coaching: string;
  niche_languages: string;
  niche_philosophy: string;
  niche_health: string;
  niche_fitness: string;
  "niche_mental-health": string;
  niche_psychology: string;
  niche_sexology: string;
  niche_nutrition: string;
  niche_yoga: string;
  niche_medicine: string;
  niche_biohacking: string;
  niche_beauty: string;
  niche_fashion: string;
  niche_hair: string;
  niche_nails: string;
  niche_lifestyle: string;
  niche_travel: string;
  niche_food: string;
  niche_sustainability: string;
  niche_gardening: string;
  niche_productivity: string;
  niche_automotive: string;
  niche_outdoor: string;
  "niche_home-decor": string;
  niche_immigration: string;
  niche_fishing: string;
  niche_parenting: string;
  niche_relationships: string;
  niche_family: string;
  niche_pregnancy: string;
  niche_wedding: string;
  niche_astrology: string;
  niche_tarot: string;
  niche_numerology: string;
  niche_religion: string;
  niche_spirituality: string;
  "niche_energy-practices": string;
  "niche_human-design": string;
  "niche_true-crime": string;
  niche_entertainment: string;
  niche_comedy: string;
  niche_memes: string;
  niche_gaming: string;
  niche_anime: string;
  niche_asmr: string;
  niche_books: string;
  niche_cinema: string;
  niche_sports: string;
  "niche_martial-arts": string;
  "niche_extreme-sports": string;
  niche_esports: string;
  niche_pets: string;
  niche_dogs: string;
  niche_cats: string;
  niche_wildlife: string;
  niche_news: string;
  niche_politics: string;
  niche_economics: string;
  niche_history: string;
  niche_military: string;
  "niche_self-development": string;
  niche_other: string;
  // Niche group labels
  niche_group_tech_ai: string;
  niche_group_business_money: string;
  niche_group_marketing_growth: string;
  niche_group_creative: string;
  niche_group_education_career: string;
  niche_group_health_wellness: string;
  niche_group_beauty_fashion: string;
  niche_group_lifestyle: string;
  niche_group_family_relationships: string;
  niche_group_spirituality_esoteric: string;
  niche_group_entertainment: string;
  niche_group_sports: string;
  niche_group_pets_animals: string;
  niche_group_news_society: string;
  niche_group_other: string;

  // Niche settings
  settings_niches: string;
  settings_niches_hint: string;
  settings_niches_auto_hint: string;

  // Interest settings
  settings_interests: string;
  settings_interests_hint: string;
  settings_interests_auto_hint: string;
  settings_interests_empty: string;

  // Content Radar
  settings_radar_title: string;
  settings_radar_hint: string;
  settings_radar_no_telegram: string;
  settings_radar_enabled: string;
  settings_radar_mode: string;
  settings_radar_mode_instant: string;
  settings_radar_mode_digest: string;
  settings_radar_mode_both: string;
  settings_radar_min_x: string;
  settings_radar_min_x_hint: string;
  settings_radar_quiet_hours: string;
  settings_radar_quiet_hours_hint: string;
  settings_radar_niches: string;
  settings_radar_niches_hint: string;

  // HomePage steps
  home_step_link: string;
  home_step_ai: string;
  home_step_script: string;
    home_benefits_title: string;
    home_feat_hooks_t: string;
    home_feat_hooks_d: string;
    home_feat_struct_t: string;
    home_feat_struct_d: string;
    home_feat_retain_t: string;
    home_feat_retain_d: string;
    home_feat_script_t: string;
    home_feat_script_d: string;
    home_cta_title: string;
    home_cta_sub: string;
    home_cta_btn: string;

  // AI Refine
  refine_improve: string;
  refine_strengthen_hook: string;
  refine_shorten: string;
  refine_add_specifics: string;
  refine_rewrite_opening: string;
  refine_simplify: string;
  refine_stronger_cta: string;
  refine_add_emojis: string;
  refine_more_detail: string;
  refine_input_placeholder: string;
  refine_send: string;
  refine_cancel: string;
  refine_stop: string;
  refine_generating: string;
  refine_result: string;
  refine_accept: string;
  refine_reject: string;
  refine_try_again: string;
  refine_daily_limit_reached: string;

  // Onboarding
  onboarding_title: string;
  onboarding_subtitle: string;
  onboarding_ig_btn: string;
  onboarding_ig_desc: string;
  onboarding_manual_btn: string;
  onboarding_manual_desc: string;
  onboarding_skip: string;
  onboarding_banner: string;

  // Onboarding - tone options
  onboarding_tone_conversational: string;
  onboarding_tone_conversational_desc: string;
  onboarding_tone_expert: string;
  onboarding_tone_expert_desc: string;
  onboarding_tone_energetic: string;
  onboarding_tone_energetic_desc: string;
  onboarding_tone_calm: string;
  onboarding_tone_calm_desc: string;

  // Onboarding - deep analysis status
  onboarding_da_scraping: string;
  onboarding_da_downloading: string;
  onboarding_da_transcribing: string;
  onboarding_da_analyzing_frames: string;
  onboarding_da_extracting_patterns: string;
  onboarding_da_analyzing_posts: string;
  onboarding_da_generating_profile: string;
  onboarding_da_done: string;
  onboarding_da_loading: string;
  onboarding_da_continues: string;
  onboarding_da_checking: string;
  onboarding_da_interrupted: string;
  onboarding_da_error: string;
  onboarding_da_ready: string;
  onboarding_da_starting: string;
  onboarding_da_time_estimate: string;

  // Onboarding - time units
  onboarding_time_sec: string;
  onboarding_time_min: string;
  onboarding_time_remaining: string;

  // Onboarding - from scratch step
  onboarding_scratch_title: string;
  onboarding_scratch_blog_label: string;
  onboarding_scratch_blog_placeholder: string;
  onboarding_scratch_niche_label: string;
  onboarding_scratch_tone_label: string;
  onboarding_scratch_saving: string;
  onboarding_scratch_save: string;
  onboarding_tell_blog: string;
  onboarding_select_niche: string;
  onboarding_save_error: string;

  // Onboarding - instagram step
  onboarding_ig_step_title: string;
  onboarding_ig_step_desc: string;
  onboarding_ig_step_placeholder: string;
  onboarding_ig_step_analyze: string;
  onboarding_ig_step_hint: string;
  onboarding_enter_username: string;

  // Onboarding - analyzing step
  onboarding_analyzing_title: string;
  onboarding_open_analysis: string;
  onboarding_done_tooltip: string;
  onboarding_minimize: string;

  // Onboarding - completion state
  onboarding_completed_title: string;
  onboarding_completed_desc: string;
  onboarding_completed_view: string;
  onboarding_tag_tone: string;
  onboarding_tag_niches: string;
  onboarding_tag_interests: string;
  onboarding_tag_video_format: string;
  onboarding_tag_cta: string;

  // Onboarding - review step
  onboarding_review_title: string;
  onboarding_review_desc: string;
  onboarding_review_about: string;
  onboarding_review_tone: string;
  onboarding_review_niches: string;
  onboarding_review_interests: string;
  onboarding_review_video_format: string;
  onboarding_review_script_cta: string;
  onboarding_review_desc_cta: string;
  onboarding_review_forbidden: string;
  onboarding_review_patterns: string;
  onboarding_review_saving: string;
  onboarding_review_save: string;
  onboarding_review_skip: string;
  onboarding_format_head_visual: string;
  onboarding_format_head_only: string;
  onboarding_format_screencast: string;

  // Settings - auto-profile section
  settings_autoprofile_title: string;
  settings_autoprofile_desc: string;
  settings_autoprofile_filled: string;
  settings_autoprofile_reanalyze: string;
  settings_autoprofile_updated: string;
  settings_autoprofile_placeholder: string;
  settings_autoprofile_analyze: string;
  settings_autoprofile_hint: string;

  // Upgrade modal
  upgrade_authors_title: string;
  upgrade_authors_desc: string;
  upgrade_trends_title: string;
  upgrade_trends_search: string;
  upgrade_trends_pages: string;
  upgrade_used_label: string;
  upgrade_limit_reached: string;
  upgrade_used_pct: string;
  upgrade_switch_to: string;
  upgrade_analyses_for: string;
  upgrade_price_monthly: string;
  upgrade_go_to: string;
  upgrade_later: string;

  // Auth callback
  auth_callback_error: string;
  auth_callback_link_expired: string;
  auth_callback_link_used: string;
  auth_callback_link_not_found: string;
  auth_callback_send_new_link: string;
  auth_callback_home: string;

  // Payment failed banner
  payment_failed_banner: string;
  payment_failed_banner_btn: string;

  // Cookie consent
  cookie_message: string;
  cookie_accept: string;
  cookie_reject: string;
  cookie_learn_more: string;

  // Footer
  footer_terms: string;
  footer_privacy: string;
  footer_cookies: string;
  footer_refund: string;

  // Personal data consent
  consent_personal_data: string;

  // Telegram settings
  settings_telegram_title: string;
  settings_telegram_connect: string;
  settings_telegram_disconnect: string;
  settings_telegram_description: string;
  settings_telegram_linked_as: string;
  settings_telegram_disconnecting: string;

  // Telegram hero (settings top block when not connected)
  settings_telegram_hero_title: string;
  settings_telegram_hero_vp1: string;
  settings_telegram_hero_vp2: string;
  settings_telegram_hero_vp3: string;
  settings_telegram_hero_vp4: string;

  // Linked accounts
  settings_linked_accounts: string;
  settings_linked_accounts_none: string;
  settings_linked_accounts_not_linked: string;
  settings_linked_accounts_link: string;
  settings_linked_accounts_warning: string;
  settings_linked_accounts_warning_analyses: string;

  // Telegram promo (contextual prompts)
  tg_promo_processing_title: string;
  tg_promo_processing_desc: string;
  tg_promo_trends_title: string;
  tg_promo_trends_desc: string;
  tg_promo_results_title: string;
  tg_promo_results_desc: string;
  tg_promo_connect: string;
  tg_promo_not_now: string;
  tg_promo_stop: string;
  tg_promo_connected: string;
  tg_promo_banner_no_bot: string;

  // Delete account
  settings_delete_account: string;
  settings_delete_account_hint: string;
  settings_delete_account_btn: string;
  settings_delete_account_confirm_title: string;
  settings_delete_account_confirm_message: string;
  settings_delete_account_confirm_btn: string;
  settings_delete_account_cancel: string;
  settings_delete_account_deleting: string;

  // Refund Policy page
  refund_title: string;
  refund_intro: string;
  refund_right_title: string;
  refund_right_text: string;
  refund_how_title: string;
  refund_how_text: string;
  refund_timeline_title: string;
  refund_timeline_text: string;
  refund_exceptions_title: string;
  refund_exceptions_text: string;
  refund_contact_title: string;
  refund_contact_text: string;

  // Terms of Service / Оферта page (17 разделов)
  terms_title: string;
  terms_intro: string;
  terms_definitions_title: string;
  terms_definitions_text: string;
  terms_subject_title: string;
  terms_subject_text: string;
  terms_acceptance_title: string;
  terms_acceptance_text: string;
  terms_pricing_title: string;
  terms_pricing_text: string;
  terms_payment_title: string;
  terms_payment_text: string;
  terms_recurring_title: string;
  terms_recurring_text: string;
  terms_cancellation_title: string;
  terms_cancellation_text: string;
  terms_obligations_title: string;
  terms_obligations_text: string;
  terms_ai_title: string;
  terms_ai_text: string;
  terms_liability_title: string;
  terms_liability_text: string;
  terms_ip_title: string;
  terms_ip_text: string;
  terms_personaldata_title: string;
  terms_personaldata_text: string;
  terms_termination_title: string;
  terms_termination_text: string;
  terms_modifications_title: string;
  terms_modifications_text: string;
  terms_disputes_title: string;
  terms_disputes_text: string;
  terms_forcemajeure_title: string;
  terms_forcemajeure_text: string;
  terms_contact_title: string;
  terms_contact_text: string;

  // Privacy Policy page
  privacy_title: string;
  privacy_intro: string;
  privacy_data_title: string;
  privacy_data_text: string;
  privacy_purposes_title: string;
  privacy_purposes_text: string;
  privacy_legal_title: string;
  privacy_legal_text: string;
  privacy_sharing_title: string;
  privacy_sharing_text: string;
  privacy_retention_title: string;
  privacy_retention_text: string;
  privacy_rights_title: string;
  privacy_rights_text: string;
  privacy_security_title: string;
  privacy_security_text: string;
  privacy_changes_title: string;
  privacy_changes_text: string;
  privacy_contact_title: string;
  privacy_contact_text: string;

  // Cookie Policy page
  cookie_policy_title: string;
  cookie_policy_intro: string;
  cookie_policy_what_title: string;
  cookie_policy_what_text: string;
  cookie_policy_types_title: string;
  cookie_policy_essential_title: string;
  cookie_policy_essential_text: string;
  cookie_policy_functional_title: string;
  cookie_policy_functional_text: string;
  cookie_policy_analytics_title: string;
  cookie_policy_analytics_text: string;
  cookie_policy_manage_title: string;
  cookie_policy_manage_text: string;
  cookie_policy_contact_title: string;
  cookie_policy_contact_text: string;

  // Multi-provider auth
  modal_register_title: string;
  modal_choose_method: string;
  modal_auto_register_hint: string;
  modal_oauth_yandex: string;
  modal_oauth_google: string;
  modal_or: string;
  modal_email_login: string;
  modal_back: string;
  modal_email_enter: string;
  modal_email_send: string;
  modal_email_sent: string;
  modal_email_check_inbox: string;
  modal_email_code_placeholder: string;
  modal_email_verify: string;
  modal_email_or_link: string;
  modal_email_wrong_code: string;
  modal_email_code_expired: string;
  modal_email_resend: string;

  // Consent step
  consent_step_title: string;
  consent_terms_accept: string;
  consent_continue: string;

  // Meta disclaimer (RU only)
  footer_meta_disclaimer: string;

  // Teaser (anonymous gating)
  teaser_cta_title: string;
  teaser_cta_subtitle: string;
  teaser_cta_button: string;
  teaser_locked: string;
  teaser_frames_hint: string;
  teaser_transcript_hint: string;

  // Script Rating
  rating_title: string;
  rating_comment_placeholder: string;
  rating_submit: string;
  rating_thanks: string;

  // Support Chat
  support_chat_title: string;
  support_placeholder: string;
  support_consent: string;
  support_consent_link: string;
  support_send: string;
  support_empty: string;
  support_welcome_name: string;
}

export type TranslationKey = keyof Translations;

export const SUPPORTED_LANGUAGES = ["ru", "en", "fr", "pt", "de"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

export const LANGUAGE_LABELS: Record<SupportedLanguage, string> = {
  ru: "Русский",
  en: "English",
  fr: "Français",
  pt: "Português",
  de: "Deutsch",
};

export const LANGUAGE_FLAGS: Record<SupportedLanguage, string> = {
  ru: "🇷🇺",
  en: "🇺🇸",
  fr: "🇫🇷",
  pt: "🇧🇷",
  de: "🇩🇪",
};
