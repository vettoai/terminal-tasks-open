class CampaignsController < ActionController::API
  DATASETS = %w[camp_ops_demo camp_diamond camp_large].to_h do |campaign|
    [campaign, JSON.parse(File.read(Rails.root.join('fixtures', "#{campaign}.json")))]
  end.freeze
  %w[tasks dependencies events].each do |collection|
    define_method(collection) do
      campaign = DATASETS[params[:campaign_id]]
      return head :not_found unless campaign
      render json: { collection => campaign.fetch(collection) }
    end
  end
end
