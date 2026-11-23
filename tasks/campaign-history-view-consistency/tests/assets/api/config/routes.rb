Rails.application.routes.draw do
  get '/api/campaigns/:campaign_id/tasks', to: 'campaigns#tasks'
  get '/api/campaigns/:campaign_id/dependencies', to: 'campaigns#dependencies'
  get '/api/campaigns/:campaign_id/events', to: 'campaigns#events'
end
